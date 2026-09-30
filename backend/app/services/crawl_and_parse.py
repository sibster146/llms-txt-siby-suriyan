"""Combined page crawling, content extraction, and workflow orchestration."""

from __future__ import annotations

import gzip
import io
import ipaddress
import json
import logging
import posixpath
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from uuid import uuid4

import trafilatura
from lxml import etree, html
from markdown_it import MarkdownIt

from app.clients.dynamodb import DynamoDBConditionNotMetError
from app.tables.crawl_pages import TERMINAL_PAGE_STATUSES, CrawlPagesTable

SUPPORTED_CONTENT_TYPES = {
    "application/xhtml+xml",
    "text/html",
    "text/markdown",
    "text/x-markdown",
}
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class WebCrawlerError(Exception):
    """Raised when a queued page cannot be crawled safely."""


class CrawlMessageError(WebCrawlerError):
    """Raised when an SQS message does not match the crawl contract."""


class UnsafeUrlError(WebCrawlerError):
    """Raised when a URL could access a non-public network destination."""


class RobotsDeniedError(WebCrawlerError):
    """Raised when robots.txt disallows the requested page."""


class UnsupportedContentTypeError(WebCrawlerError):
    """Raised when a response is not a supported crawlable document."""


class ResponseTooLargeError(WebCrawlerError):
    """Raised when a response exceeds the configured byte limit."""


class PageNotFoundError(WebCrawlerError):
    """Raised when a page returns HTTP 404 and should not be retried."""


@dataclass(frozen=True)
class CrawlRequest:
    site_id: str
    crawl_run_id: str
    root_url: str
    url: str
    canonical_url_hash: str
    depth: int

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> CrawlRequest:
        """Validate a crawl SQS message and return its immutable request fields.

        Called before reading workflow records. Require the crawl_url action,
        nonempty identifiers, nonnegative depth, and a SHA-256 matching the URL.
        URL shape is checked here; public DNS checks happen before fetching.
        Raise CrawlMessageError or UnsafeUrlError for invalid input.
        """
        if message.get("action") != "crawl_url":
            raise CrawlMessageError("Crawl message action must be 'crawl_url'")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise CrawlMessageError("Crawl message payload must be an object")

        site_id = _required_string(payload, "site_id")
        crawl_run_id = _required_string(payload, "crawl_run_id")
        root_url = _required_string(payload, "root_url")
        url = _required_string(payload, "url")
        canonical_url_hash = _required_string(payload, "canonical_url_hash")
        depth = payload.get("depth")
        if not isinstance(depth, int) or isinstance(depth, bool) or depth < 0:
            raise CrawlMessageError("Crawl message depth must be a non-negative integer")
        if not SHA256_PATTERN.fullmatch(canonical_url_hash):
            raise CrawlMessageError("canonical_url_hash must be a lowercase SHA-256 hash")
        if sha256(url.encode()).hexdigest() != canonical_url_hash:
            raise CrawlMessageError("canonical_url_hash does not match the URL")
        _validate_url_shape(url)
        _validate_url_shape(root_url)

        return cls(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
            root_url=root_url,
            url=url,
            canonical_url_hash=canonical_url_hash,
            depth=depth,
        )


@dataclass(frozen=True)
class FetchedPage:
    content: bytes
    content_type: str
    final_url: str
    http_status: int
    etag: str | None = None
    last_modified: str | None = None


FetchPage = Callable[[str, str, float, int], FetchedPage]
RobotsChecker = Callable[[str, str, float], bool]


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        """Check a page or robots redirect's public destination before following it."""
        redirect_url = urljoin(req.full_url, newurl)
        validate_public_url(redirect_url)
        return super().redirect_request(req, fp, code, msg, headers, redirect_url)


def fetch_html_page(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    max_response_bytes: int,
) -> FetchedPage:
    """Fetch bounded HTML or Markdown bytes and response metadata for a page.

    Used when a page has no saved raw checkpoint. Check public destinations,
    including redirects, and enforce content-type and response-size limits.
    Translate HTTP 404 into a nonretryable PageNotFoundError; wrap other network
    failures in WebCrawlerError so the service can apply its retry policy.
    """
    validate_public_url(url)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,text/markdown;q=0.9",
            "Accept-Encoding": "identity",
            "User-Agent": user_agent,
        },
    )
    try:
        with build_opener(_SafeRedirectHandler()).open(
            request, timeout=timeout_seconds
        ) as response:
            final_url = response.geturl()
            validate_public_url(final_url)
            content_type = response.headers.get_content_type().lower()
            if content_type not in SUPPORTED_CONTENT_TYPES:
                raise UnsupportedContentTypeError(
                    f"Expected HTML or Markdown from '{url}', received '{content_type}'"
                )
            content = _read_limited(response, max_response_bytes)
            return FetchedPage(
                content=content,
                content_type=content_type,
                final_url=final_url,
                http_status=int(response.status),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
    except WebCrawlerError:
        raise
    except HTTPError as error:
        if error.code == 404:
            raise PageNotFoundError(f"Page not found at '{url}'") from error
        raise WebCrawlerError(f"Failed to fetch '{url}': {error}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise WebCrawlerError(f"Failed to fetch '{url}': {error}") from error


def robots_allows(url: str, user_agent: str, timeout_seconds: float) -> bool:
    """Check robots.txt before fetching a page without a raw checkpoint.

    Evaluate rules for the configured user agent. Deny HTTP 401/403 responses;
    allow other HTTP errors or ordinary network failures. Public-URL validation
    and the robots response-size limit can still raise crawler errors.
    """
    validate_public_url(url)
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    request = Request(
        robots_url,
        headers={"Accept": "text/plain,*/*;q=0.1", "User-Agent": user_agent},
    )
    try:
        with build_opener(_SafeRedirectHandler()).open(
            request, timeout=timeout_seconds
        ) as response:
            rules = _read_limited(response, 512_000).decode("utf-8", errors="replace")
    except HTTPError as error:
        return error.code not in {401, 403}
    except (URLError, TimeoutError, OSError):
        return True

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(rules.splitlines())
    return parser.can_fetch(user_agent, url)


def validate_public_url(url: str) -> None:
    """Reject unsafe URL shapes or any non-global resolved IP before HTTP access.

    Check all DNS results, raising UnsafeUrlError for resolution failure or a
    non-public address. This is a preflight check, not a pinned DNS connection.
    """
    parsed = _validate_url_shape(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise UnsafeUrlError(f"Could not resolve URL host '{parsed.hostname}'") from error

    if not addresses:
        raise UnsafeUrlError(f"URL host '{parsed.hostname}' did not resolve")
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeUrlError(f"URL host '{parsed.hostname}' resolved to a non-public address")


def _validate_url_shape(url: str) -> Any:
    """Return URL components after rejecting non-HTTP, credentialed, or localhost URLs.

    Used for message validation and fetch preflight; this performs no DNS lookup.
    """
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("URL must use HTTP or HTTPS and include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".localhost"):
        raise UnsafeUrlError("Localhost URLs are not allowed")
    return parsed


def _read_limited(response: Any, max_response_bytes: int) -> bytes:
    """Read a response with a one-byte overflow probe; raise if it exceeds the cap."""
    content = response.read(max_response_bytes + 1)
    if len(content) > max_response_bytes:
        raise ResponseTooLargeError(f"Response exceeds the {max_response_bytes}-byte crawl limit")
    return content


def _required_string(payload: dict[str, Any], field: str) -> str:
    """Return a stripped message field or raise CrawlMessageError if it is blank."""
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CrawlMessageError(f"Crawl message {field} must be a non-empty string")
    return value.strip()


class HtmlParserError(Exception):
    """The downloaded document could not be parsed."""


SKIPPED_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".eot",
    ".exe",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mov",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".rss",
    ".svg",
    ".tar",
    ".tif",
    ".tiff",
    ".ttf",
    ".wav",
    ".webp",
    ".woff",
    ".woff2",
    ".xls",
    ".xlsx",
    ".xml",
    ".zip",
}
HTML_CONTENT_TYPES = {"application/xhtml+xml", "text/html"}
MARKDOWN_CONTENT_TYPES = {"text/markdown", "text/x-markdown"}
SITEMAP_MAX_BYTES = 2_000_000
SITEMAP_MAX_DOCUMENTS = 10
SITEMAP_TIMEOUT_SECONDS = 3
SITEMAP_USER_AGENT = "llms-txt-crawler/1.0"


def extract_child_urls(
    document: Any,
    *,
    root_url: str,
    final_url: str,
    depth: int,
    max_depth: int,
    max_links: int,
) -> list[str]:
    """Return sorted, unique in-scope HTML links for child registration.

    Stop discovery at max_depth, skip nofollow links and excluded file types,
    and cap results at max_links. Resolve relative links against final_url or
    an in-scope HTML base element. Exclude the root URL itself.
    """
    if depth >= max_depth:
        return []

    base_url = final_url
    base_nodes = document.xpath("//base[@href][1]/@href")
    if base_nodes:
        candidate_base = urljoin(final_url, str(base_nodes[0]))
        if is_url_within_root(candidate_base, root_url, include_root=True):
            base_url = candidate_base

    child_urls: set[str] = set()
    for anchor in document.xpath("//a[@href]"):
        rel = {part.lower() for part in str(anchor.get("rel", "")).split()}
        if "nofollow" in rel:
            continue
        canonical_url = canonicalize_discovered_url(urljoin(base_url, str(anchor.get("href", ""))))
        if canonical_url is None:
            continue
        if not is_url_within_root(canonical_url, root_url):
            continue
        child_urls.add(canonical_url)
        if len(child_urls) >= max_links:
            break
    return sorted(child_urls)


def extract_markdown_child_urls(
    raw_markdown: bytes,
    *,
    root_url: str,
    final_url: str,
    depth: int,
    max_depth: int,
    max_links: int,
) -> list[str]:
    """Extract bounded, unique child links directly from Markdown tokens.

    Used instead of the HTML tree extractor for Markdown responses. Resolve
    relative links against final_url, apply root and file-type filters, and
    return sorted URLs unless the page has already reached max_depth.
    """
    if depth >= max_depth:
        return []

    markdown_text = raw_markdown.decode("utf-8", errors="replace")
    child_urls: set[str] = set()
    for token in MarkdownIt("commonmark").parse(markdown_text):
        for child in token.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href")
            canonical_url = canonicalize_discovered_url(urljoin(final_url, href or ""))
            if canonical_url is None:
                continue
            if not is_url_within_root(canonical_url, root_url):
                continue
            child_urls.add(canonical_url)
            if len(child_urls) >= max_links:
                return sorted(child_urls)
    return sorted(child_urls)


def is_url_within_root(candidate_url: str, root_url: str, *, include_root: bool = False) -> bool:
    """Check discovery scope by scheme, hostname, effective port, and root path.

    Used for links, base elements, and sitemap results. Match path boundaries,
    not arbitrary prefixes; include the root path only when include_root is true.
    """
    try:
        candidate = urlsplit(candidate_url)
        root = urlsplit(root_url)
        candidate_port = candidate.port or (443 if candidate.scheme.lower() == "https" else 80)
        root_port = root.port or (443 if root.scheme.lower() == "https" else 80)
    except ValueError:
        return False
    if (
        candidate.scheme.lower() != root.scheme.lower()
        or (candidate.hostname or "").lower() != (root.hostname or "").lower()
        or candidate_port != root_port
    ):
        return False

    root_path = (root.path or "/").rstrip("/") or "/"
    candidate_path = (candidate.path or "/").rstrip("/") or "/"
    if candidate_path == root_path:
        return include_root
    if root_path == "/":
        return candidate_path.startswith("/")
    return candidate_path.startswith(f"{root_path}/")


def discover_sitemap_urls(root_url: str, max_urls: int) -> list[str]:
    """Supplement root-page links with up to max_urls unique sitemap URLs.

    Try /sitemap.xml and same-origin Sitemap entries from robots.txt, following
    sitemap indexes up to SITEMAP_MAX_DOCUMENTS. Filter page URLs to crawl scope
    and supported extensions; skip unavailable or invalid sitemap documents.
    """
    if max_urls <= 0:
        return []
    root = urlsplit(root_url)
    origin = urlunsplit((root.scheme, root.netloc, "", "", ""))
    sitemap_urls = [urljoin(origin, "/sitemap.xml")]
    robots_text = _fetch_discovery_resource(urljoin(origin, "/robots.txt"), text=True)
    if isinstance(robots_text, str):
        for line in robots_text.splitlines():
            name, separator, value = line.partition(":")
            if separator and name.strip().lower() == "sitemap":
                sitemap_url = urljoin(origin, value.strip())
                if _same_origin(sitemap_url, root_url):
                    sitemap_urls.append(sitemap_url)

    discovered: list[str] = []
    seen_pages: set[str] = set()
    seen_sitemaps: set[str] = set()
    pending_sitemaps = list(dict.fromkeys(sitemap_urls))
    while pending_sitemaps and len(seen_sitemaps) < SITEMAP_MAX_DOCUMENTS:
        sitemap_url = pending_sitemaps.pop(0)
        if sitemap_url in seen_sitemaps or not _same_origin(sitemap_url, root_url):
            continue
        seen_sitemaps.add(sitemap_url)
        payload = _fetch_discovery_resource(sitemap_url)
        if not isinstance(payload, bytes):
            continue
        for location, is_index in _parse_sitemap(payload, sitemap_url):
            if is_index:
                normalized_sitemap_url = _normalize_http_url(location)
                if normalized_sitemap_url and _same_origin(normalized_sitemap_url, root_url):
                    pending_sitemaps.append(normalized_sitemap_url)
                continue
            canonical_url = canonicalize_discovered_url(location)
            if canonical_url is None:
                continue
            if canonical_url in seen_pages or not is_url_within_root(canonical_url, root_url):
                continue
            seen_pages.add(canonical_url)
            discovered.append(canonical_url)
            if len(discovered) >= max_urls:
                return discovered
    return discovered


class _DiscoveryRedirectHandler(HTTPRedirectHandler):
    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Request | None:
        """Validate public destinations before following robots or sitemap redirects."""
        redirect_url = urljoin(req.full_url, newurl)
        validate_public_url(redirect_url)
        return super().redirect_request(req, fp, code, msg, headers, redirect_url)


def _fetch_discovery_resource(url: str, *, text: bool = False) -> bytes | str | None:
    """Fetch an optional robots/sitemap resource with bounded size and timeout.

    Bound both downloaded and gzip-expanded bytes. Return decoded UTF-8 when
    text is true, otherwise bytes; return None for oversized data or caught
    HTTP, network, gzip, and value errors. UnsafeUrlError is not suppressed.
    """
    try:
        validate_public_url(url)
        request = Request(url, headers={"User-Agent": SITEMAP_USER_AGENT})
        with build_opener(_DiscoveryRedirectHandler()).open(
            request,
            timeout=SITEMAP_TIMEOUT_SECONDS,
        ) as response:
            payload = response.read(SITEMAP_MAX_BYTES + 1)
            if len(payload) > SITEMAP_MAX_BYTES:
                return None
            content_encoding = str(response.headers.get("Content-Encoding", "")).lower()
            if content_encoding == "gzip" or urlsplit(url).path.lower().endswith(".gz"):
                with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:
                    payload = compressed.read(SITEMAP_MAX_BYTES + 1)
                if len(payload) > SITEMAP_MAX_BYTES:
                    return None
            return payload.decode("utf-8", errors="replace") if text else payload
    except (HTTPError, URLError, OSError, ValueError):
        return None


def _parse_sitemap(payload: bytes, sitemap_url: str) -> list[tuple[str, bool]]:
    """Return resolved loc URLs paired with whether they belong to a sitemap index.

    Disable XML entity resolution and network access. Discovery treats malformed
    XML or unsupported root elements as an empty list.
    """
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False)
        root = etree.fromstring(payload, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        return []
    root_name = etree.QName(root).localname.lower()
    if root_name not in {"urlset", "sitemapindex"}:
        return []
    is_index = root_name == "sitemapindex"
    locations = root.xpath("//*[local-name()='loc']/text()")
    return [(urljoin(sitemap_url, str(location).strip()), is_index) for location in locations]


def _same_origin(first_url: str, second_url: str) -> bool:
    """Compare origins without restricting paths when selecting sitemap documents."""
    second = urlsplit(second_url)
    origin = urlunsplit((second.scheme, second.netloc, "/", "", ""))
    return is_url_within_root(first_url, origin, include_root=True)


def _normalize_http_url(url: str) -> str | None:
    """Normalize a discovered HTTP URL, or return None for invalid scheme/host/port.

    Lowercase scheme and hostname, omit default ports and fragments, and ensure
    a path exists. Preserve query strings and path spelling for URL identity.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = (
        parsed.hostname.lower()
        if port is None or default_port
        else f"{parsed.hostname.lower()}:{port}"
    )
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _merge_discovered_urls(primary: list[str], secondary: list[str], limit: int) -> list[str]:
    """Deduplicate discovery lists in order up to a positive limit, primary first.

    Root-page discovery uses this to prioritize sitemap URLs over extracted links.
    """
    merged: list[str] = []
    seen: set[str] = set()
    for url in [*primary, *secondary]:
        if url in seen:
            continue
        seen.add(url)
        merged.append(url)
        if len(merged) >= limit:
            break
    return merged


def canonicalize_discovered_url(url: str) -> str | None:
    """Normalize a discovered URL and reject excluded asset/document extensions.

    Called before scope checks and child URL hashing. Return None for rejected
    links; public DNS validation is deferred until the page is fetched.
    """
    normalized_url = _normalize_http_url(url)
    if normalized_url is None:
        return None
    parsed = urlsplit(normalized_url)
    path = parsed.path or "/"
    suffix = posixpath.splitext(path.lower())[1]
    if suffix in SKIPPED_EXTENSIONS:
        return None
    return normalized_url


def extract_page_content(
    raw_html: bytes,
    document: Any,
    final_url: str,
    raw_html_hash: str,
    parser_version: str,
) -> dict[str, Any]:
    """Build the parsed JSON payload from HTML for storage and later generation.

    Use trafilatura for main-content Markdown and metadata, falling back to the
    HTML tree for title, description, and language. Include headings, source
    URL/hash, parser version, and parse time. This function does not write to S3.
    """
    html_text = raw_html.decode("utf-8", errors="replace")
    main_content = (
        trafilatura.extract(
            html_text,
            url=final_url,
            output_format="markdown",
            include_formatting=True,
            include_links=True,
            include_images=False,
            favor_precision=True,
        )
        or ""
    )
    metadata = trafilatura.extract_metadata(html_text, default_url=final_url)
    title = _metadata_value(metadata, "title") or _first_text(document, "//title")
    description = _metadata_value(metadata, "description") or _meta_description(document)
    language = _metadata_value(metadata, "language") or _document_language(document)
    headings = [
        {"level": str(node.tag).lower(), "text": _clean_text(node.text_content())}
        for node in document.xpath("//h1|//h2|//h3|//h4|//h5|//h6")
        if _clean_text(node.text_content())
    ]
    return {
        "url": final_url,
        "title": title,
        "description": description,
        "language": language,
        "headings": headings,
        "main_content": main_content,
        "raw_html_hash": raw_html_hash,
        "parser_version": parser_version,
        "parsed_at": now(),
    }


def extract_markdown_content(
    raw_markdown: bytes,
    final_url: str,
    raw_html_hash: str,
    parser_version: str,
) -> dict[str, Any]:
    """Build the parsed payload for a Markdown response without an HTML tree.

    Use the first H1 as title and first paragraph as description; keep headings
    and the stripped Markdown body. Include source/hash/version/time metadata
    and leave language unset. The caller persists the result in S3.
    """
    markdown_text = raw_markdown.decode("utf-8", errors="replace").strip()
    tokens = MarkdownIt("commonmark").parse(markdown_text)
    headings: list[dict[str, str]] = []
    title: str | None = None
    description: str | None = None

    for index, token in enumerate(tokens):
        if token.type == "heading_open" and index + 1 < len(tokens):
            heading_text = _clean_text(tokens[index + 1].content)
            if heading_text:
                headings.append({"level": token.tag.lower(), "text": heading_text})
                if token.tag.lower() == "h1" and title is None:
                    title = heading_text
        elif token.type == "paragraph_open" and index + 1 < len(tokens) and description is None:
            paragraph_text = _clean_text(tokens[index + 1].content)
            if paragraph_text:
                description = paragraph_text

    return {
        "url": final_url,
        "title": title,
        "description": description,
        "language": None,
        "headings": headings,
        "main_content": markdown_text,
        "raw_html_hash": raw_html_hash,
        "parser_version": parser_version,
        "parsed_at": now(),
    }


def _parse_document(raw_html: bytes, base_url: str) -> Any:
    """Create a recoverable, non-networking lxml HTML tree for links and metadata.

    Attach base_url for relative references and wrap value/type parsing errors
    in HtmlParserError for the service's failure handling.
    """
    try:
        return html.fromstring(
            raw_html,
            base_url=base_url,
            parser=html.HTMLParser(recover=True, no_network=True),
        )
    except (ValueError, TypeError) as error:
        raise HtmlParserError(f"Unable to parse HTML: {error}") from error


def _metadata_value(metadata: Any, name: str) -> str | None:
    """Read and clean a trafilatura metadata field, returning None when empty."""
    value = getattr(metadata, name, None) if metadata is not None else None
    cleaned = _clean_text(str(value)) if value else ""
    return cleaned or None


def _first_text(document: Any, xpath: str) -> str | None:
    """Return cleaned text of the first matched HTML element for metadata fallback."""
    nodes = document.xpath(xpath)
    if not nodes:
        return None
    cleaned = _clean_text(nodes[0].text_content())
    return cleaned or None


def _meta_description(document: Any) -> str | None:
    """Read the first case-insensitive description meta tag as a metadata fallback."""
    values = document.xpath(
        "//meta[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz')='description']/@content"
    )
    cleaned = _clean_text(str(values[0])) if values else ""
    return cleaned or None


def _document_language(document: Any) -> str | None:
    """Read the HTML lang attribute when extracted metadata lacks a language."""
    values = document.xpath("/html/@lang")
    cleaned = _clean_text(str(values[0])) if values else ""
    return cleaned or None


def _clean_text(value: str) -> str:
    """Collapse whitespace and trim extracted headings, text, and metadata."""
    return " ".join(value.split())


logger = logging.getLogger(__name__)


class WorkDeferred(Exception):
    """Another worker owns the page/run, or its retry delay has not elapsed."""


def now() -> str:
    """Return the current UTC ISO timestamp for workflow records and lease checks."""
    return datetime.now(UTC).isoformat()


def after(seconds: int) -> str:
    """Return a UTC ISO timestamp offset from now for leases and retry deadlines."""
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


class CrawlAndParseService:
    """One page per invocation, with recoverable dispatch and fenced ownership."""

    def __init__(
        self,
        *,
        crawl_pages,
        crawl_runs,
        sites,
        s3,
        crawl_queue,
        llm_txt_queue,
        user_agent: str,
        request_timeout_seconds: float,
        max_response_bytes: int,
        max_attempts: int,
        retry_delay_seconds: int,
        lease_seconds: int,
        parser_version: str,
        max_depth: int,
        max_links_per_page: int,
        max_discovered_pages: int,
        fetch_page=fetch_html_page,
        robots_checker=robots_allows,
        sitemap_discoverer=discover_sitemap_urls,
    ):
        """Configure table/client dependencies, crawl limits, and recovery timing.

        Store the supplied dependencies without performing I/O. Fetch, robots,
        and sitemap callables can be replaced in tests. max_attempts limits
        crawl/parse attempts; the table layer defines the separate children cap.
        """
        self.pages = crawl_pages
        self.runs = crawl_runs
        self.sites = sites
        self.s3 = s3
        self.crawl_queue = crawl_queue
        self.generation_queue = llm_txt_queue
        self.user_agent = user_agent
        self.request_timeout = request_timeout_seconds
        self.max_bytes = max_response_bytes
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay_seconds
        self.lease_seconds = lease_seconds
        self.parser_version = parser_version
        self.max_depth = max_depth
        self.max_links = max_links_per_page
        self.max_pages = max_discovered_pages
        self.fetch_page = fetch_page
        self.robots_checker = robots_checker
        self.sitemap_discoverer = sitemap_discoverer

    def process_message(self, message: dict[str, Any]) -> None:
        """Handle one crawl message under an atomic, token-fenced page claim.

        Ignore deleted or finished work, resume raw/parsed checkpoints, register
        children, then finish the page. Permanent errors or exhausted attempts
        fail the page; other failures persist and dispatch a delayed retry.
        Discovery-lock contention refunds the children attempt. Ownership
        conflicts raise WorkDeferred. After a terminal page update, check whether
        the run can generate; pending dispatch can also be recovered later.
        """
        request = CrawlRequest.from_message(message)
        page = self.pages.get(
            crawl_run_id=request.crawl_run_id, canonical_url_hash=request.canonical_url_hash
        )
        if page is None:
            return  # A deleted run must not be recreated by an old message.
        if page["site_id"] != request.site_id or page["url"] != request.url:
            raise ValueError("Message does not match its stored page")
        run = self.runs.get(site_id=page["site_id"], crawl_run_id=page["crawl_run_id"])
        if run is None or run["status"] in {"FAILED", "COMPLETED"}:
            return
        if page["status"] in TERMINAL_PAGE_STATUSES:
            self.check_generation(run)
            return
        if run["status"] == "GENERATING":
            return
        if self.pages.attempts_exhausted(page, self.max_attempts):
            if not self.pages.fail_abandoned(
                page,
                now=now(),
                error=(
                    "Children attempts exhausted"
                    if page.get("parsed_content_s3_key")
                    else "Processing attempts exhausted"
                ),
            ):
                raise WorkDeferred("A worker still owns the page")
            self.check_generation(run)
            return
        token = str(uuid4())
        if not self.pages.claim(
            page,
            runs_table_name=self.runs.dynamodb.table_name,
            token=token,
            now=now(),
            expires_at=after(self.lease_seconds),
            max_attempts=self.max_attempts,
        ):
            raise WorkDeferred("Page owned by another worker or retry not yet due")
        # Read our claimed attempt number; subsequent mutations are fenced by token.
        page = self.pages.get(**self.pages.key(page))
        resuming_children = bool(page.get("parsed_content_s3_key"))
        try:
            children = self._crawl_and_parse(page, token)
            if not resuming_children:
                self.pages.start_children_attempt(page, token=token, now=now())
            self._register_children(page, token, children)
            self.pages.finish(page, token=token, now=now())
        except WorkDeferred as error:
            # Lock contention is waiting, not a failed children-processing attempt.
            self.pages.retry(
                page,
                token=token,
                now=now(),
                retry_after=after(self.retry_delay),
                error=str(error),
                refund_children_attempt=True,
            )
            retry = self.pages.get(**self.pages.key(page))
            self.dispatch(retry, delay=self.retry_delay)
            return
        except DynamoDBConditionNotMetError as error:
            raise WorkDeferred("Worker or discovery lease changed") from error
        except Exception as error:
            current = self.pages.get(**self.pages.key(page))
            if current is None or current.get("worker_token") != token:
                raise WorkDeferred("Ownership changed") from error
            terminal = isinstance(
                error,
                (
                    PageNotFoundError,
                    ResponseTooLargeError,
                    RobotsDeniedError,
                    UnsafeUrlError,
                    UnsupportedContentTypeError,
                ),
            ) or self.pages.attempts_exhausted(current, self.max_attempts)
            if terminal:
                self.pages.finish(current, token=token, now=now(), error=str(error))
            else:
                self.pages.retry(
                    current,
                    token=token,
                    now=now(),
                    retry_after=after(self.retry_delay),
                    error=str(error),
                )
                retry = self.pages.get(**self.pages.key(page))
                self.dispatch(retry, delay=self.retry_delay)
                return
        self.check_generation(run)

    def _crawl_and_parse(self, page: dict, token: str) -> list[str]:
        """Persist raw/parsed checkpoints and return child URLs for the claimed page.

        Reuse saved raw bytes on retries; otherwise check robots, fetch, hash,
        and save a content-addressed S3 object before its DynamoDB checkpoint.
        Replay site change timestamps when needed. Always extract links from raw
        content, supplementing the root with sitemap discovery. Reuse parsed S3
        content by parser version, raw hash, and final URL, saving its reference
        before children are registered. Update the passed page with checkpoint
        fields and children_root_url; all page writes require the worker token.
        """
        if page.get("raw_html_s3_key"):
            raw = self.s3.get_bytes(page["raw_html_s3_key"])
        else:
            if not self.robots_checker(page["url"], self.user_agent, self.request_timeout):
                raise RobotsDeniedError("robots.txt disallows this URL")
            fetched = self.fetch_page(
                page["url"], self.user_agent, self.request_timeout, self.max_bytes
            )
            raw = fetched.content
            digest = sha256(raw).hexdigest()
            previous = self.pages.get_latest_crawled(
                site_id=page["site_id"], canonical_url_hash=page["canonical_url_hash"]
            )
            unchanged = bool(previous and previous.get("raw_html_hash") == digest)
            extension = "md" if fetched.content_type in MARKDOWN_CONTENT_TYPES else "html"
            key = f"raw/{page['site_id']}/{page['canonical_url_hash']}/{digest}.{extension}"
            if not self.s3.object_exists(key):
                self.s3.put_bytes(key=key, content=raw, content_type=fetched.content_type)
            timestamp = now()
            result = dict(
                raw_html_s3_key=key,
                raw_html_hash=digest,
                final_url=fetched.final_url,
                content_type=fetched.content_type,
                crawled_at=timestamp,
                http_status=fetched.http_status,
                content_length=len(raw),
                raw_html_changed=not unchanged,
            )
            self.pages.save_result(page, token=token, now=timestamp, result=result)
            page.update(result)

        # Replay this idempotent site update if an earlier attempt stopped after saving raw data.
        if page.get("raw_html_changed"):
            self.sites.mark_content_changed(
                site_id=page["site_id"],
                crawl_run_id=page["crawl_run_id"],
                modified_at=page["crawled_at"],
            )

        root = page["final_url"] if int(page["depth"]) == 0 else page["root_url"]
        args = dict(
            root_url=root,
            final_url=page["final_url"],
            depth=int(page["depth"]),
            max_depth=self.max_depth,
            max_links=self.max_links,
        )
        content_type = page["content_type"]
        if content_type in HTML_CONTENT_TYPES:
            document = _parse_document(raw, page["final_url"])
            children = extract_child_urls(document, **args)
        elif content_type in MARKDOWN_CONTENT_TYPES:
            document = None
            children = extract_markdown_child_urls(raw, **args)
        else:
            raise UnsupportedContentTypeError(content_type)
        if page["depth"] == 0 and self.max_depth > 0:
            sitemap = self.sitemap_discoverer(root, self.max_links)
            children = _merge_discovered_urls(
                [url for url in sitemap if is_url_within_root(url, root)],
                children,
                self.max_links,
            )
        # Include the final URL in the key: relative URLs can differ for identical HTML.
        final_hash = sha256(page["final_url"].encode()).hexdigest()
        parsed_key = (
            f"parsed/{self.parser_version}/{page['site_id']}/{page['canonical_url_hash']}/"
            f"{page['raw_html_hash']}-{final_hash}.json"
        )
        if not self.s3.object_exists(parsed_key):
            if document is None:
                parsed = extract_markdown_content(
                    raw, page["final_url"], page["raw_html_hash"], self.parser_version
                )
            else:
                parsed = extract_page_content(
                    raw, document, page["final_url"], page["raw_html_hash"], self.parser_version
                )
            self.s3.put_text(
                key=parsed_key,
                content=json.dumps(parsed, ensure_ascii=True),
                content_type="application/json",
            )
        self.pages.save_result(
            page, token=token, now=now(), result={"parsed_content_s3_key": parsed_key}
        )
        page["parsed_content_s3_key"] = parsed_key
        page["children_root_url"] = root
        return children

    def _register_children(self, parent: dict, worker_token: str, children: list[str]) -> None:
        """Register unique children under the run lock, then dispatch outside it.

        For each batch of 50 links, reload existing pages to deduplicate hashes
        and enforce the run-wide cap, including the root. Transactional inserts
        require both discovery-lock and parent-worker ownership. Raise WorkDeferred
        when the discovery lock is busy. Finally resend this parent's children
        whose dispatch intent remains pending from an interrupted attempt.
        """
        run_key = dict(site_id=parent["site_id"], crawl_run_id=parent["crawl_run_id"])
        # Each short transaction batch gets a fresh lock and a fresh capacity calculation.
        for offset in range(0, len(children), 50):
            token = str(uuid4())
            if not self.runs.acquire_discovery_lock(
                **run_key, token=token, now=now(), expires_at=after(30)
            ):
                raise WorkDeferred("Another worker is registering children")
            try:
                existing = self.pages.list_for_run(parent["crawl_run_id"])
                hashes = {p["canonical_url_hash"] for p in existing}
                capacity = max(0, self.max_pages - len(existing))
                new = []
                for url in children[offset : offset + 50]:
                    digest = sha256(url.encode()).hexdigest()
                    if digest in hashes or len(new) >= capacity:
                        continue
                    hashes.add(digest)
                    new.append(
                        CrawlPagesTable.new_item(
                            **run_key,
                            canonical_url_hash=digest,
                            url=url,
                            root_url=parent["children_root_url"],
                            depth=int(parent["depth"]) + 1,
                            parent_url=parent["url"],
                            created_at=now(),
                        )
                    )
                if new:
                    self.pages.register_children(
                        parent,
                        new,
                        runs_table_name=self.runs.dynamodb.table_name,
                        lock_token=token,
                        worker_token=worker_token,
                        now=now(),
                    )
            finally:
                self.runs.release_discovery_lock(**run_key, token=token)
            for child in new:
                self.dispatch(child)
        # A previous attempt may have registered children and crashed before sending.
        for child in self.pages.list_for_run(parent["crawl_run_id"]):
            if child.get("parent_url") == parent["url"] and child.get("dispatch_pending"):
                self.dispatch(child)

    def dispatch(self, page: dict, *, delay: int = 0) -> None:
        """Send a nonterminal page to crawl SQS, then record dispatch acceptance.

        Used for new children, retries, and recovery. delay is the SQS delay in
        seconds; dispatch_after allows later recovery if processing never starts.
        Sending before mark_sent preserves recoverability but can yield duplicate
        messages, which must pass the page's ownership and status checks.
        """
        if page["status"] in TERMINAL_PAGE_STATUSES:
            return
        self.crawl_queue.send_json(
            {
                "action": "crawl_url",
                "payload": {
                    "site_id": page["site_id"],
                    "crawl_run_id": page["crawl_run_id"],
                    "canonical_url_hash": page["canonical_url_hash"],
                    "url": page["url"],
                    "root_url": page["root_url"],
                    "depth": int(page["depth"]),
                },
            },
            delay_seconds=delay,
        )
        self.pages.mark_sent(page, dispatch_after=after(self.lease_seconds + delay))

    def check_generation(self, run: dict) -> None:
        """Check page completion under the discovery lock and dispatch generation.

        Called after terminal page processing and by recovery. Wait for every
        page to be terminal; fail the run if all failed, otherwise atomically
        claim GENERATING. Send only when generation_dispatch_pending is set,
        clearing it after queue acceptance. An already-generating run can retry
        dispatch without repeating page checks; deleted/terminal runs are ignored.
        """
        key = dict(site_id=run["site_id"], crawl_run_id=run["crawl_run_id"])
        current = self.runs.get(**key)
        if current is None or current["status"] in {"COMPLETED", "FAILED"}:
            return
        if current["status"] != "GENERATING":
            token = str(uuid4())
            if not self.runs.acquire_discovery_lock(
                **key, token=token, now=now(), expires_at=after(30)
            ):
                return  # Periodic recovery also performs this check.
            try:
                pages = self.pages.list_for_run(run["crawl_run_id"])
                if not pages or any(p["status"] not in TERMINAL_PAGE_STATUSES for p in pages):
                    return
                if all(p["status"] == "FAILED" for p in pages):
                    self.runs.fail_empty_run(**key, token=token, updated_at=now())
                    return
                if not self.runs.claim_generation(**key, token=token, updated_at=now()):
                    return
            finally:
                self.runs.release_discovery_lock(**key, token=token)
            current = self.runs.get(**key)
        if current.get("generation_dispatch_pending"):
            self.generation_queue.send_json({"action": "generate_llms_txt", "payload": key})
            self.runs.mark_generation_sent(**key)

    def process_dead_letter(self, message: dict) -> None:
        """Reprocess a crawl DLQ message through normal claim and attempt checks.

        SQS receive counts do not determine failure; stored processing/children
        attempts and page ownership decide whether to work, defer, or fail.
        """
        # Transport receives are not processing attempts. The same claim rules apply.
        self.process_message(message)

    def recover(self, remaining_ms=lambda: 120000) -> None:
        """Sweep active runs for abandoned work and pending generation dispatch.

        The periodic recovery invocation skips terminal pages, valid leases,
        and future retry times. Fail expired exhausted attempts; otherwise resend
        unsent or overdue work, then check generation readiness. remaining_ms is
        a callable reporting the invocation budget; stop below ten seconds.
        Log per-run errors and leave them for a later sweep, with no sweep limit.
        """
        for run in self.runs.list_active():
            if remaining_ms() < 10000:
                return
            try:
                if run["status"] != "GENERATING":
                    for page in self.pages.list_for_run(run["crawl_run_id"]):
                        if remaining_ms() < 10000:
                            return
                        timestamp = now()
                        if page["status"] in TERMINAL_PAGE_STATUSES:
                            continue
                        if page.get("lease_expires_at", "") > timestamp:
                            continue
                        if page.get("retry_after", "") > timestamp:
                            continue
                        if self.pages.attempts_exhausted(page, self.max_attempts):
                            self.pages.fail_abandoned(
                                page,
                                now=timestamp,
                                error=(
                                    "Worker stopped before completing its final children attempt"
                                    if page.get("parsed_content_s3_key")
                                    else "Worker stopped before completing its final attempt"
                                ),
                            )
                        elif (
                            page.get("dispatch_pending")
                            or page.get("dispatch_after", "") <= timestamp
                        ):
                            self.dispatch(page)
                self.check_generation(run)
            except Exception:
                logger.exception("Recovery failed for crawl %s", run["crawl_run_id"])
