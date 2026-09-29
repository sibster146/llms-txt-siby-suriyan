from __future__ import annotations

import gzip
import io
import json
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import trafilatura
from lxml import etree, html
from markdown_it import MarkdownIt

from app.clients.s3 import S3Client
from app.clients.sqs import SQSClient, SQSClientError
from app.services.web_crawler import validate_public_url
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
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
ACTIVE_PAGE_STATUSES = {
    "DISCOVERED",
    "PENDING",
    "CRAWLING",
    "CRAWLED",
    "PARSE_PENDING",
    "PARSING",
}
PARSING_LEASE_SECONDS = 120
HTML_CONTENT_TYPES = {"application/xhtml+xml", "text/html"}
MARKDOWN_CONTENT_TYPES = {"text/markdown", "text/x-markdown"}
SITEMAP_MAX_BYTES = 2_000_000
SITEMAP_MAX_DOCUMENTS = 10
SITEMAP_TIMEOUT_SECONDS = 3
SITEMAP_USER_AGENT = "llms-txt-crawler/1.0"


class HtmlParserError(Exception):
    """Raised when a parser queue message cannot be processed."""


class ParseMessageError(HtmlParserError):
    """Raised when a parser queue message does not match the contract."""


@dataclass(frozen=True)
class ParseRequest:
    site_id: str
    crawl_run_id: str
    root_url: str
    url: str
    final_url: str
    canonical_url_hash: str
    depth: int
    raw_html_s3_key: str
    unchanged: bool

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> ParseRequest:
        if message.get("action") != "parse_page":
            raise ParseMessageError("Parser message action must be 'parse_page'")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise ParseMessageError("Parser message payload must be an object")

        request = cls(
            site_id=_required_string(payload, "site_id"),
            crawl_run_id=_required_string(payload, "crawl_run_id"),
            root_url=_required_string(payload, "root_url"),
            url=_required_string(payload, "url"),
            final_url=_required_string(payload, "final_url"),
            canonical_url_hash=_required_string(payload, "canonical_url_hash"),
            depth=_required_non_negative_int(payload, "depth"),
            raw_html_s3_key=_required_string(payload, "raw_html_s3_key"),
            unchanged=_required_bool(payload, "unchanged"),
        )
        if not SHA256_PATTERN.fullmatch(request.canonical_url_hash):
            raise ParseMessageError("canonical_url_hash must be a lowercase SHA-256 hash")
        if sha256(request.url.encode()).hexdigest() != request.canonical_url_hash:
            raise ParseMessageError("canonical_url_hash does not match the URL")
        if request.depth > 0 and not is_url_within_root(
            request.url,
            request.root_url,
            include_root=True,
        ):
            raise ParseMessageError("url is outside the root URL hierarchy")
        return request


SitemapDiscoverer = Callable[[str, int], list[str]]


class HtmlParserService:
    """Extract page content and enqueue same-site links for crawling."""

    def __init__(
        self,
        *,
        crawl_pages: CrawlPagesTable,
        crawl_runs: CrawlRunsTable,
        s3: S3Client,
        crawl_queue: SQSClient,
        llm_txt_queue: SQSClient,
        parser_version: str,
        max_depth: int,
        max_links_per_page: int,
        max_discovered_pages: int,
        max_attempts: int,
        sitemap_discoverer: SitemapDiscoverer | None = None,
    ) -> None:
        self.crawl_pages = crawl_pages
        self.crawl_runs = crawl_runs
        self.s3 = s3
        self.crawl_queue = crawl_queue
        self.llm_txt_queue = llm_txt_queue
        self.parser_version = parser_version
        self.max_depth = max_depth
        self.max_links_per_page = max_links_per_page
        self.max_discovered_pages = max_discovered_pages
        self.max_attempts = max_attempts
        self.sitemap_discoverer = sitemap_discoverer or discover_sitemap_urls

    def process_message(self, message: dict[str, Any], attempt: int = 1) -> None:
        request = ParseRequest.from_message(message)
        page_record = self.crawl_pages.get(
            crawl_run_id=request.crawl_run_id,
            canonical_url_hash=request.canonical_url_hash,
        )
        if page_record is None:
            raise HtmlParserError("CrawlPages record does not exist")
        if page_record.get("site_id") != request.site_id:
            raise HtmlParserError("Parser message does not match the stored site")

        if page_record.get("status") == "PARSED":
            self._publish_generation_if_complete(request)
            return
        if page_record.get("status") == "FAILED":
            self._publish_generation_if_complete(request)
            return

        raw_html_hash = str(page_record.get("raw_html_hash", ""))
        if not SHA256_PATTERN.fullmatch(raw_html_hash):
            raise HtmlParserError("CrawlPages record is missing raw_html_hash")
        if page_record.get("raw_html_s3_key") != request.raw_html_s3_key:
            raise HtmlParserError("Parser message does not match the stored raw HTML key")

        started_at = datetime.now(UTC)
        claimed = self.crawl_pages.claim_parsing(
            crawl_run_id=request.crawl_run_id,
            canonical_url_hash=request.canonical_url_hash,
            claimed_at=started_at.isoformat(),
            lease_expires_at=(started_at + timedelta(seconds=PARSING_LEASE_SECONDS)).isoformat(),
        )
        if not claimed:
            return

        try:
            raw_html = self.s3.get_bytes(request.raw_html_s3_key)
            content_type = (
                str(page_record.get("content_type", "text/html")).split(";", 1)[0].lower()
            )
            if content_type in HTML_CONTENT_TYPES:
                document = _parse_document(raw_html, request.final_url)
                child_urls = extract_child_urls(
                    document,
                    root_url=request.root_url,
                    final_url=request.final_url,
                    depth=request.depth,
                    max_depth=self.max_depth,
                    max_links=self.max_links_per_page,
                )
            elif content_type in MARKDOWN_CONTENT_TYPES:
                document = None
                child_urls = extract_markdown_child_urls(
                    raw_html,
                    root_url=request.root_url,
                    final_url=request.final_url,
                    depth=request.depth,
                    max_depth=self.max_depth,
                    max_links=self.max_links_per_page,
                )
            else:
                raise HtmlParserError(f"Unsupported parser content type '{content_type}'")
            if request.depth == 0 and request.depth < self.max_depth:
                sitemap_urls = self.sitemap_discoverer(
                    request.root_url,
                    self.max_links_per_page,
                )
                child_urls = _merge_discovered_urls(
                    sitemap_urls,
                    child_urls,
                    self.max_links_per_page,
                )
            parsed_key = self._parsed_content_key(
                request.site_id,
                request.canonical_url_hash,
                raw_html_hash,
            )
            if not request.unchanged or not self.s3.object_exists(parsed_key):
                if content_type in MARKDOWN_CONTENT_TYPES:
                    parsed_content = extract_markdown_content(
                        raw_html,
                        request.final_url,
                        raw_html_hash,
                        self.parser_version,
                    )
                else:
                    parsed_content = extract_page_content(
                        raw_html,
                        document,
                        request.final_url,
                        raw_html_hash,
                        self.parser_version,
                    )
                parsed_content["source_content_type"] = content_type
                self.s3.put_text(
                    key=parsed_key,
                    content=json.dumps(parsed_content, ensure_ascii=True, separators=(",", ":")),
                    content_type="application/json; charset=utf-8",
                    metadata={
                        "site-id": request.site_id,
                        "raw-html-sha256": raw_html_hash,
                        "parser-version": self.parser_version,
                    },
                )

            self._queue_child_pages(request, child_urls)
            parsed_at = _utc_now()
            self.crawl_pages.mark_parsed(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=request.canonical_url_hash,
                parsed_content_s3_key=parsed_key,
                parsed_at=parsed_at,
            )
            run_counts = self.crawl_runs.record_parsed_page(
                site_id=request.site_id,
                crawl_run_id=request.crawl_run_id,
                updated_at=parsed_at,
            )
            self._publish_generation_if_complete(request, run_counts)
        except Exception as error:
            self.crawl_pages.record_parse_failure(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=request.canonical_url_hash,
                error_message=str(error),
                attempt=attempt,
                terminal=attempt >= self.max_attempts,
                updated_at=_utc_now(),
            )
            raise

    def _parsed_content_key(
        self,
        site_id: str,
        canonical_url_hash: str,
        raw_html_hash: str,
    ) -> str:
        return f"parsed/{self.parser_version}/{site_id}/{canonical_url_hash}/{raw_html_hash}.json"

    def _queue_child_pages(
        self,
        request: ParseRequest,
        child_urls: list[str],
    ) -> None:
        timestamp = _utc_now()
        for child_url in child_urls:
            child_hash = sha256(child_url.encode()).hexdigest()
            child = self.crawl_pages.get(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=child_hash,
            )
            if child is not None:
                if child.get("status") == "DISCOVERED":
                    self._queue_child_page(request, child_url, child_hash)
                continue

            reserved = self.crawl_runs.reserve_discovered_page(
                site_id=request.site_id,
                crawl_run_id=request.crawl_run_id,
                max_discovered_pages=self.max_discovered_pages,
                updated_at=timestamp,
            )
            if not reserved:
                break

            try:
                created = self.crawl_pages.create_if_absent(
                    crawl_run_id=request.crawl_run_id,
                    canonical_url_hash=child_hash,
                    site_id=request.site_id,
                    url=child_url,
                    depth=request.depth + 1,
                    parent_url=request.final_url,
                    created_at=timestamp,
                )
            except Exception:
                self.crawl_runs.release_discovered_page(
                    site_id=request.site_id,
                    crawl_run_id=request.crawl_run_id,
                    updated_at=_utc_now(),
                )
                raise

            if not created:
                self.crawl_runs.release_discovered_page(
                    site_id=request.site_id,
                    crawl_run_id=request.crawl_run_id,
                    updated_at=_utc_now(),
                )
                continue

            self._queue_child_page(request, child_url, child_hash)

    def _queue_child_page(
        self,
        request: ParseRequest,
        child_url: str,
        child_hash: str,
    ) -> None:
        self.crawl_queue.send_json(
            {
                "action": "crawl_url",
                "payload": {
                    "site_id": request.site_id,
                    "crawl_run_id": request.crawl_run_id,
                    "root_url": request.root_url,
                    "url": child_url,
                    "canonical_url_hash": child_hash,
                    "depth": request.depth + 1,
                },
            }
        )
        self.crawl_pages.mark_queued(
            crawl_run_id=request.crawl_run_id,
            canonical_url_hash=child_hash,
            updated_at=_utc_now(),
        )

    def _publish_generation_if_complete(
        self,
        request: ParseRequest,
        run_counts: dict[str, Any] | None = None,
    ) -> None:
        if run_counts is not None and not _run_counts_complete(run_counts):
            return
        pages = self.crawl_pages.list_for_run(request.crawl_run_id)
        if not pages or any(page.get("status") in ACTIVE_PAGE_STATUSES for page in pages):
            return
        claimed = self.crawl_runs.claim_generation(
            site_id=request.site_id,
            crawl_run_id=request.crawl_run_id,
            updated_at=_utc_now(),
        )
        if not claimed:
            return
        try:
            self.llm_txt_queue.send_json(
                {
                    "action": "generate_llms_txt",
                    "payload": {
                        "site_id": request.site_id,
                        "crawl_run_id": request.crawl_run_id,
                    },
                }
            )
        except SQSClientError:
            self.crawl_runs.release_generation_claim(
                site_id=request.site_id,
                crawl_run_id=request.crawl_run_id,
                updated_at=_utc_now(),
            )
            raise


def extract_child_urls(
    document: Any,
    *,
    root_url: str,
    final_url: str,
    depth: int,
    max_depth: int,
    max_links: int,
) -> list[str]:
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
    """Return whether a URL is on the same origin and below the root path."""
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
    """Discover in-scope URLs from robots.txt and bounded sitemap traversal."""
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
        redirect_url = urljoin(req.full_url, newurl)
        validate_public_url(redirect_url)
        return super().redirect_request(req, fp, code, msg, headers, redirect_url)


def _fetch_discovery_resource(url: str, *, text: bool = False) -> bytes | str | None:
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
    second = urlsplit(second_url)
    origin = urlunsplit((second.scheme, second.netloc, "/", "", ""))
    return is_url_within_root(first_url, origin, include_root=True)


def _normalize_http_url(url: str) -> str | None:
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
        "parsed_at": _utc_now(),
    }


def extract_markdown_content(
    raw_markdown: bytes,
    final_url: str,
    raw_html_hash: str,
    parser_version: str,
) -> dict[str, Any]:
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
        "parsed_at": _utc_now(),
    }


def _parse_document(raw_html: bytes, base_url: str) -> Any:
    try:
        return html.fromstring(
            raw_html,
            base_url=base_url,
            parser=html.HTMLParser(recover=True, no_network=True),
        )
    except (ValueError, TypeError) as error:
        raise HtmlParserError(f"Unable to parse HTML: {error}") from error


def _metadata_value(metadata: Any, name: str) -> str | None:
    value = getattr(metadata, name, None) if metadata is not None else None
    cleaned = _clean_text(str(value)) if value else ""
    return cleaned or None


def _first_text(document: Any, xpath: str) -> str | None:
    nodes = document.xpath(xpath)
    if not nodes:
        return None
    cleaned = _clean_text(nodes[0].text_content())
    return cleaned or None


def _meta_description(document: Any) -> str | None:
    values = document.xpath(
        "//meta[translate(@name, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz')='description']/@content"
    )
    cleaned = _clean_text(str(values[0])) if values else ""
    return cleaned or None


def _document_language(document: Any) -> str | None:
    values = document.xpath("/html/@lang")
    cleaned = _clean_text(str(values[0])) if values else ""
    return cleaned or None


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _required_string(payload: dict[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ParseMessageError(f"{name} must be a non-empty string")
    return value.strip()


def _required_non_negative_int(payload: dict[str, Any], name: str) -> int:
    value = payload.get(name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ParseMessageError(f"{name} must be a non-negative integer")
    return value


def _required_bool(payload: dict[str, Any], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise ParseMessageError(f"{name} must be a boolean")
    return value


def _run_counts_complete(run: dict[str, Any]) -> bool:
    try:
        pending = int(run["pending_page_count"])
        discovered = int(run["discovered_page_count"])
        completed = int(run["completed_page_count"])
        failed = int(run["failed_page_count"])
    except (KeyError, TypeError, ValueError):
        return False
    return pending == 0 and completed + failed == discovered


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
