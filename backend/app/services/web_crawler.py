from __future__ import annotations

import ipaddress
import json
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from app.clients.s3 import S3Client
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable

HTML_CONTENT_TYPES = {"application/xhtml+xml", "text/html"}
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
    """Raised when a response is not HTML."""


class ResponseTooLargeError(WebCrawlerError):
    """Raised when a response exceeds the configured byte limit."""


@dataclass(frozen=True)
class CrawlRequest:
    site_id: str
    crawl_run_id: str
    url: str
    canonical_url_hash: str
    depth: int

    @classmethod
    def from_message(cls, message: dict[str, Any]) -> CrawlRequest:
        if message.get("action") != "crawl_url":
            raise CrawlMessageError("Crawl message action must be 'crawl_url'")
        payload = message.get("payload")
        if not isinstance(payload, dict):
            raise CrawlMessageError("Crawl message payload must be an object")

        site_id = _required_string(payload, "site_id")
        crawl_run_id = _required_string(payload, "crawl_run_id")
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

        return cls(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
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


class WebCrawlerService:
    """Fetch queued web pages and hand their stored HTML to the parser queue."""

    def __init__(
        self,
        *,
        crawl_pages: CrawlPagesTable,
        crawl_runs: CrawlRunsTable,
        s3: S3Client,
        sqs_client: Any,
        parse_queue_url: str,
        user_agent: str,
        request_timeout_seconds: float,
        max_response_bytes: int,
        max_attempts: int,
        fetch_page: FetchPage | None = None,
        robots_checker: RobotsChecker | None = None,
    ) -> None:
        self.crawl_pages = crawl_pages
        self.crawl_runs = crawl_runs
        self.s3 = s3
        self.sqs_client = sqs_client
        self.parse_queue_url = parse_queue_url
        self.user_agent = user_agent
        self.request_timeout_seconds = request_timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_attempts = max_attempts
        self.fetch_page = fetch_page or fetch_html_page
        self.robots_checker = robots_checker or robots_allows

    def process_message(self, message: dict[str, Any], attempt: int = 1) -> None:
        request = CrawlRequest.from_message(message)

        try:
            existing_page = self.crawl_pages.get(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=request.canonical_url_hash,
            )
            existing_status = (existing_page or {}).get("status")
            if existing_status == "PARSE_PENDING":
                self.crawl_runs.update_status(
                    site_id=request.site_id,
                    crawl_run_id=request.crawl_run_id,
                    crawl_status="CRAWLED",
                    updated_at=_utc_now(),
                )
                return
            if existing_status == "COMPLETED":
                return

            self.crawl_runs.update_status(
                site_id=request.site_id,
                crawl_run_id=request.crawl_run_id,
                crawl_status="WORKING",
                updated_at=_utc_now(),
            )

            raw_html_s3_key = str((existing_page or {}).get("raw_html_s3_key", ""))
            final_url = str((existing_page or {}).get("final_url", request.url))
            if not raw_html_s3_key:
                raw_html_s3_key, final_url = self._fetch_and_store(request)

            self._publish_parse_message(request, raw_html_s3_key, final_url)
            self.crawl_pages.mark_parse_pending(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=request.canonical_url_hash,
                updated_at=_utc_now(),
            )
            self.crawl_runs.update_status(
                site_id=request.site_id,
                crawl_run_id=request.crawl_run_id,
                crawl_status="CRAWLED",
                updated_at=_utc_now(),
            )
        except Exception as error:
            self.crawl_pages.record_failure(
                crawl_run_id=request.crawl_run_id,
                canonical_url_hash=request.canonical_url_hash,
                error_message=str(error),
                attempt=attempt,
                terminal=attempt >= self.max_attempts,
                updated_at=_utc_now(),
            )
            raise

    def _fetch_and_store(self, request: CrawlRequest) -> tuple[str, str]:
        self.crawl_pages.mark_crawling(
            crawl_run_id=request.crawl_run_id,
            canonical_url_hash=request.canonical_url_hash,
            updated_at=_utc_now(),
        )
        if not self.robots_checker(
            request.url,
            self.user_agent,
            self.request_timeout_seconds,
        ):
            raise RobotsDeniedError(f"robots.txt disallows '{request.url}'")

        page = self.fetch_page(
            request.url,
            self.user_agent,
            self.request_timeout_seconds,
            self.max_response_bytes,
        )
        crawled_at = _utc_now()
        raw_html_s3_key = (
            f"raw/{request.site_id}/{request.crawl_run_id}/"
            f"{request.canonical_url_hash}.html"
        )
        self.s3.put_bytes(
            key=raw_html_s3_key,
            content=page.content,
            content_type=page.content_type,
            metadata={
                "site-id": request.site_id,
                "crawl-run-id": request.crawl_run_id,
                "url-sha256": request.canonical_url_hash,
            },
        )
        self.crawl_pages.mark_crawled(
            crawl_run_id=request.crawl_run_id,
            canonical_url_hash=request.canonical_url_hash,
            raw_html_s3_key=raw_html_s3_key,
            final_url=page.final_url,
            http_status=page.http_status,
            content_type=page.content_type,
            content_length=len(page.content),
            crawled_at=crawled_at,
            etag=page.etag,
            last_modified=page.last_modified,
        )
        return raw_html_s3_key, page.final_url

    def _publish_parse_message(
        self,
        request: CrawlRequest,
        raw_html_s3_key: str,
        final_url: str,
    ) -> None:
        body = {
            "action": "parse_page",
            "payload": {
                "site_id": request.site_id,
                "crawl_run_id": request.crawl_run_id,
                "url": request.url,
                "final_url": final_url,
                "canonical_url_hash": request.canonical_url_hash,
                "depth": request.depth,
                "raw_html_s3_key": raw_html_s3_key,
            },
        }
        self.sqs_client.send_message(
            QueueUrl=self.parse_queue_url,
            MessageBody=json.dumps(body, separators=(",", ":")),
        )


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
        redirect_url = urljoin(req.full_url, newurl)
        validate_public_url(redirect_url)
        return super().redirect_request(req, fp, code, msg, headers, redirect_url)


def fetch_html_page(
    url: str,
    user_agent: str,
    timeout_seconds: float,
    max_response_bytes: int,
) -> FetchedPage:
    validate_public_url(url)
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml",
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
            if content_type not in HTML_CONTENT_TYPES:
                raise UnsupportedContentTypeError(
                    f"Expected HTML from '{url}', received '{content_type}'"
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
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise WebCrawlerError(f"Failed to fetch '{url}': {error}") from error


def robots_allows(url: str, user_agent: str, timeout_seconds: float) -> bool:
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
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("URL must use HTTP or HTTPS and include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URLs containing credentials are not allowed")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(".localhost"):
        raise UnsafeUrlError("Localhost URLs are not allowed")
    return parsed


def _read_limited(response: Any, max_response_bytes: int) -> bytes:
    content = response.read(max_response_bytes + 1)
    if len(content) > max_response_bytes:
        raise ResponseTooLargeError(
            f"Response exceeds the {max_response_bytes}-byte crawl limit"
        )
    return content


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CrawlMessageError(f"Crawl message {field} must be a non-empty string")
    return value.strip()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
