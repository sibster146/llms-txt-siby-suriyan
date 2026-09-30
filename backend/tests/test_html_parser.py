import json
from hashlib import sha256
from typing import Any

import pytest

from app.clients.sqs import SQSClientError
from app.services.html_parser import (
    HtmlParserService,
    ParseMessageError,
    _parse_document,
    _run_counts_complete,
    discover_sitemap_urls,
    extract_child_urls,
    is_url_within_root,
)


def test_negative_pending_count_is_complete() -> None:
    assert _run_counts_complete({"pending_page_count": -1})


class FakeCrawlPagesTable:
    def __init__(self, root: dict[str, Any]) -> None:
        self.pages = {(str(root["crawl_run_id"]), str(root["canonical_url_hash"])): root}
        self.failures: list[dict[str, Any]] = []
        self.claims = 0

    def get(self, *, crawl_run_id: str, canonical_url_hash: str) -> dict[str, Any] | None:
        return self.pages.get((crawl_run_id, canonical_url_hash))

    def create_if_absent(self, **kwargs: Any) -> bool:
        key = (kwargs["crawl_run_id"], kwargs["canonical_url_hash"])
        if key in self.pages:
            return False
        self.pages[key] = {**kwargs, "status": "DISCOVERED"}
        return True

    def claim_parsing(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        **_: Any,
    ) -> bool:
        page = self.pages[(crawl_run_id, canonical_url_hash)]
        if page["status"] != "PARSE_PENDING":
            return False
        page["status"] = "PARSING"
        self.claims += 1
        return True

    def mark_queued(self, *, crawl_run_id: str, canonical_url_hash: str, **_: Any) -> None:
        self.pages[(crawl_run_id, canonical_url_hash)]["status"] = "PENDING"

    def mark_parsed(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        parsed_content_s3_key: str,
        **_: Any,
    ) -> None:
        page = self.pages[(crawl_run_id, canonical_url_hash)]
        page["status"] = "PARSED"
        page["parsed_content_s3_key"] = parsed_content_s3_key

    def list_for_run(self, crawl_run_id: str) -> list[dict[str, Any]]:
        return [page for (run_id, _), page in self.pages.items() if run_id == crawl_run_id]

    def record_parse_failure(self, **kwargs: Any) -> None:
        self.failures.append(kwargs)


class FakeCrawlRunsTable:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.generation_claimed = False
        self.releases = 0
        self.pending_page_count = 1
        self.discovered_page_count = 1
        self.completed_page_count = 0

    def reserve_discovered_page(self, *, max_discovered_pages: int, **_: Any) -> bool:
        if self.discovered_page_count >= max_discovered_pages:
            return False
        self.pending_page_count += 1
        self.discovered_page_count += 1
        return True

    def release_discovered_page(self, **_: Any) -> None:
        self.pending_page_count -= 1
        self.discovered_page_count -= 1

    def record_parsed_page(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        self.pending_page_count -= 1
        self.completed_page_count += 1
        return {
            "pending_page_count": self.pending_page_count,
            "discovered_page_count": self.discovered_page_count,
            "completed_page_count": self.completed_page_count,
            "failed_page_count": 0,
        }

    def claim_generation(self, **_: Any) -> bool:
        if self.generation_claimed:
            return False
        self.generation_claimed = True
        return True

    def release_generation_claim(self, **_: Any) -> None:
        self.generation_claimed = False
        self.releases += 1


class FakeS3Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.writes: list[str] = []

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def object_exists(self, key: str) -> bool:
        return key in self.objects

    def put_text(self, *, key: str, content: str, **_: Any) -> str:
        self.objects[key] = content.encode()
        self.writes.append(key)
        return key


class FakeQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_json(self, message: dict[str, Any]) -> str:
        self.messages.append(message)
        return "message-1"


class FailingQueue(FakeQueue):
    def send_json(self, message: dict[str, Any]) -> str:
        raise SQSClientError("queue unavailable")


def _message(*, unchanged: bool = False) -> dict[str, Any]:
    url = "https://example.com/"
    return {
        "action": "parse_page",
        "payload": {
            "site_id": "site-1",
            "crawl_run_id": "crawl-1",
            "root_url": url,
            "url": url,
            "final_url": url,
            "canonical_url_hash": sha256(url.encode()).hexdigest(),
            "depth": 0,
            "raw_html_s3_key": "raw/site-1/crawl-1/root.html",
            "unchanged": unchanged,
        },
    }


def _service(
    raw_html: bytes,
    *,
    unchanged: bool = False,
    existing_parsed: bool = False,
    content_type: str = "text/html",
    sitemap_urls: list[str] | None = None,
    max_discovered_pages: int = 1000,
) -> tuple[HtmlParserService, FakeCrawlPagesTable, FakeS3Client, FakeQueue, FakeQueue]:
    message = _message(unchanged=unchanged)
    payload = message["payload"]
    raw_hash = sha256(raw_html).hexdigest()
    parsed_key = f"parsed/v1/site-1/{payload['canonical_url_hash']}/{raw_hash}.json"
    objects = {payload["raw_html_s3_key"]: raw_html}
    if existing_parsed:
        objects[parsed_key] = b'{"existing":true}'
    pages = FakeCrawlPagesTable(
        {
            "site_id": "site-1",
            "crawl_run_id": "crawl-1",
            "canonical_url_hash": payload["canonical_url_hash"],
            "status": "PARSE_PENDING",
            "raw_html_s3_key": payload["raw_html_s3_key"],
            "raw_html_hash": raw_hash,
            "content_type": content_type,
        }
    )
    s3 = FakeS3Client(objects)
    crawl_queue = FakeQueue()
    llm_queue = FakeQueue()
    return (
        HtmlParserService(
            crawl_pages=pages,
            crawl_runs=FakeCrawlRunsTable(),
            s3=s3,
            crawl_queue=crawl_queue,
            llm_txt_queue=llm_queue,
            parser_version="v1",
            max_depth=3,
            max_links_per_page=20,
            max_discovered_pages=max_discovered_pages,
            max_attempts=5,
            sitemap_discoverer=lambda *_: sitemap_urls or [],
        ),
        pages,
        s3,
        crawl_queue,
        llm_queue,
    )


def test_parser_extracts_content_and_queues_only_crawlable_same_site_links() -> None:
    raw_html = b"""
        <html lang="en"><head><title>Documentation</title>
        <meta name="description" content="Product guide"></head><body>
        <main><h1>Getting started</h1><p>Useful product documentation.</p>
        <a href="/guide#intro">Guide</a><a href="/manual.pdf">PDF</a>
        <a href="https://outside.example/page">External</a>
        <a href="/private" rel="nofollow">Private</a></main></body></html>
    """
    service, pages, s3, crawl_queue, llm_queue = _service(raw_html)

    service.process_message(_message())

    assert len(s3.writes) == 1
    parsed = json.loads(s3.objects[s3.writes[0]])
    assert parsed["description"] == "Product guide"
    assert "Getting started" in parsed["main_content"]
    assert [message["payload"]["url"] for message in crawl_queue.messages] == [
        "https://example.com/guide"
    ]
    assert len(pages.pages) == 2
    assert llm_queue.messages == []


def test_parser_does_not_count_a_page_when_another_delivery_claimed_it() -> None:
    raw_html = b"<html><body><main>Content</main></body></html>"
    service, pages, s3, crawl_queue, llm_queue = _service(raw_html)
    root = next(iter(pages.pages.values()))
    root["status"] = "PARSING"

    service.process_message(_message())

    assert pages.claims == 0
    assert s3.writes == []
    assert crawl_queue.messages == []
    assert llm_queue.messages == []
    assert service.crawl_runs.calls == []


def test_unchanged_page_reuses_parsed_content_but_rediscovers_links() -> None:
    raw_html = b"<html><body><a href='/child'>Child</a></body></html>"
    service, _, s3, crawl_queue, _ = _service(
        raw_html,
        unchanged=True,
        existing_parsed=True,
    )

    service.process_message(_message(unchanged=True))

    assert s3.writes == []
    assert crawl_queue.messages[0]["payload"]["url"] == "https://example.com/child"


def test_parser_extracts_markdown_content_and_same_site_links() -> None:
    raw_markdown = b"# Ramp\n\nBusiness finance platform.\n\n[Guide](/guide)\n\n[External](https://outside.example/)"
    service, _, s3, crawl_queue, _ = _service(
        raw_markdown,
        content_type="text/markdown",
    )

    service.process_message(_message())

    parsed = json.loads(s3.objects[s3.writes[0]])
    assert parsed["title"] == "Ramp"
    assert parsed["description"] == "Business finance platform."
    assert parsed["source_content_type"] == "text/markdown"
    assert [message["payload"]["url"] for message in crawl_queue.messages] == [
        "https://example.com/guide"
    ]


def test_parser_queues_generation_when_every_page_is_terminal() -> None:
    raw_html = b"<html><body><main>Standalone page content.</main></body></html>"
    service, pages, _, _, llm_queue = _service(raw_html)

    service.process_message(_message())

    root = next(iter(pages.pages.values()))
    assert root["status"] == "PARSED"
    assert llm_queue.messages == [
        {
            "action": "generate_llms_txt",
            "payload": {"site_id": "site-1", "crawl_run_id": "crawl-1"},
        }
    ]

    service.process_message(_message())

    assert len(llm_queue.messages) == 1


def test_parser_releases_generation_claim_when_queueing_fails() -> None:
    raw_html = b"<html><body><main>Standalone page content.</main></body></html>"
    service, _, _, _, _ = _service(raw_html)
    service.llm_txt_queue = FailingQueue()

    with pytest.raises(SQSClientError):
        service.process_message(_message())

    assert service.crawl_runs.releases == 1
    assert not service.crawl_runs.generation_claimed


def test_link_discovery_stops_at_the_configured_depth() -> None:
    document = _parse_document(
        b"<html><body><a href='/child'>Child</a></body></html>",
        "https://example.com/",
    )

    assert (
        extract_child_urls(
            document,
            root_url="https://example.com/",
            final_url="https://example.com/",
            depth=3,
            max_depth=3,
            max_links=10,
        )
        == []
    )


def test_link_discovery_only_returns_urls_below_root_path() -> None:
    document = _parse_document(
        b"""
        <html><body>
        <a href='/docs/guide'>Guide</a>
        <a href='/docs/api/users'>API</a>
        <a href='/docs-old/archive'>Similar prefix</a>
        <a href='/pricing'>Pricing</a>
        </body></html>
        """,
        "https://example.com/docs/",
    )

    assert extract_child_urls(
        document,
        root_url="https://example.com/docs/",
        final_url="https://example.com/docs/",
        depth=0,
        max_depth=3,
        max_links=10,
    ) == [
        "https://example.com/docs/api/users",
        "https://example.com/docs/guide",
    ]


def test_root_parser_seeds_in_scope_sitemap_urls_before_page_links() -> None:
    raw_html = b"<html><body><a href='/from-page'>Page link</a></body></html>"
    service, _, _, crawl_queue, _ = _service(
        raw_html,
        sitemap_urls=["https://example.com/from-sitemap"],
    )

    service.process_message(_message())

    assert [message["payload"]["url"] for message in crawl_queue.messages] == [
        "https://example.com/from-sitemap",
        "https://example.com/from-page",
    ]
    assert all(
        message["payload"]["root_url"] == "https://example.com/" for message in crawl_queue.messages
    )


def test_parser_stops_discovery_at_the_run_page_limit() -> None:
    raw_html = b"""
        <html><body>
        <a href='/a'>A</a><a href='/b'>B</a><a href='/c'>C</a>
        </body></html>
    """
    service, pages, _, crawl_queue, _ = _service(
        raw_html,
        max_discovered_pages=2,
    )

    service.process_message(_message())

    assert [message["payload"]["url"] for message in crawl_queue.messages] == [
        "https://example.com/a"
    ]
    assert len(pages.pages) == 2
    assert service.crawl_runs.discovered_page_count == 2


def test_sitemap_discovery_follows_indexes_and_filters_to_root_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources: dict[str, bytes | str | None] = {
        "https://example.com/robots.txt": "Sitemap: /sitemap-index.xml\n",
        "https://example.com/sitemap.xml": None,
        "https://example.com/sitemap-index.xml": b"""
            <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <sitemap><loc>https://example.com/docs-sitemap.xml</loc></sitemap>
            </sitemapindex>
        """,
        "https://example.com/docs-sitemap.xml": b"""
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://example.com/docs/guide</loc></url>
              <url><loc>https://example.com/pricing</loc></url>
              <url><loc>https://outside.example/docs/other</loc></url>
            </urlset>
        """,
    }
    monkeypatch.setattr(
        "app.services.html_parser._fetch_discovery_resource",
        lambda url, **_: resources.get(url),
    )

    assert discover_sitemap_urls("https://example.com/docs/", 10) == [
        "https://example.com/docs/guide"
    ]


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("https://example.com/docs/guide", True),
        ("https://example.com/docs/api/users", True),
        ("https://example.com/docs", False),
        ("https://example.com/docs-old", False),
        ("https://example.com/pricing", False),
        ("https://other.example/docs/guide", False),
    ],
)
def test_url_hierarchy(candidate: str, expected: bool) -> None:
    assert is_url_within_root(candidate, "https://example.com/docs/") is expected


def test_parser_rejects_a_mismatched_url_hash() -> None:
    message = _message()
    message["payload"]["canonical_url_hash"] = "0" * 64
    service, _, _, _, _ = _service(b"<html></html>")

    with pytest.raises(ParseMessageError):
        service.process_message(message)


def test_parser_accepts_a_page_redirected_outside_the_root_hierarchy() -> None:
    message = _message()
    message["payload"]["final_url"] = "https://docs.example.com/guide"
    service, pages, _, _, _ = _service(
        b"<html><head><title>Guide</title></head><body><main>Documentation</main></body></html>"
    )

    service.process_message(message)

    page = pages.get(
        crawl_run_id="crawl-1",
        canonical_url_hash=message["payload"]["canonical_url_hash"],
    )
    assert page is not None
    assert page["status"] == "PARSED"
    assert service.crawl_runs.completed_page_count == 1
    assert service.crawl_runs.pending_page_count == 0
