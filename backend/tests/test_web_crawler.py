import json
from hashlib import sha256
from typing import Any

import pytest

from app.services.web_crawler import (
    CrawlMessageError,
    FetchedPage,
    RobotsDeniedError,
    WebCrawlerService,
)


class FakeCrawlPagesTable:
    def __init__(self, existing: dict[str, Any] | None = None) -> None:
        self.existing = existing
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, **_: Any) -> dict[str, Any] | None:
        return self.existing

    def mark_crawling(self, **kwargs: Any) -> None:
        self.calls.append(("mark_crawling", kwargs))

    def mark_crawled(self, **kwargs: Any) -> None:
        self.calls.append(("mark_crawled", kwargs))

    def mark_parse_pending(self, **kwargs: Any) -> None:
        self.calls.append(("mark_parse_pending", kwargs))

    def record_failure(self, **kwargs: Any) -> None:
        self.calls.append(("record_failure", kwargs))


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_bytes(self, *, key: str, content: bytes, **_: Any) -> str:
        self.objects[key] = content
        return key


class FakeSQSClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


def _message(url: str = "https://example.com/") -> dict[str, Any]:
    return {
        "action": "crawl_url",
        "payload": {
            "site_id": "site-1",
            "crawl_run_id": "crawl-1",
            "url": url,
            "canonical_url_hash": sha256(url.encode()).hexdigest(),
            "depth": 0,
        },
    }


def _service(
    crawl_pages: FakeCrawlPagesTable,
    s3: FakeS3Client,
    sqs: FakeSQSClient,
    *,
    robots_allowed: bool = True,
) -> WebCrawlerService:
    def fetch_page(*_: Any) -> FetchedPage:
        return FetchedPage(
            content=b"<html><title>Example</title></html>",
            content_type="text/html",
            final_url="https://example.com/",
            http_status=200,
            etag='"etag-1"',
        )

    return WebCrawlerService(
        crawl_pages=crawl_pages,
        s3=s3,
        sqs_client=sqs,
        parse_queue_url="https://sqs.example/parse",
        user_agent="llms-txt-crawler/1.0",
        request_timeout_seconds=10,
        max_response_bytes=1_000_000,
        max_attempts=5,
        fetch_page=fetch_page,
        robots_checker=lambda *_: robots_allowed,
    )


def test_crawler_stores_html_and_queues_parsing() -> None:
    crawl_pages = FakeCrawlPagesTable(existing={"status": "PENDING"})
    s3 = FakeS3Client()
    sqs = FakeSQSClient()

    _service(crawl_pages, s3, sqs).process_message(_message())

    key = next(iter(s3.objects))
    assert key.startswith("raw/site-1/crawl-1/")
    assert s3.objects[key].startswith(b"<html>")
    assert [name for name, _ in crawl_pages.calls] == [
        "mark_crawling",
        "mark_crawled",
        "mark_parse_pending",
    ]
    queued = json.loads(sqs.messages[0]["MessageBody"])
    assert queued["action"] == "parse_page"
    assert queued["payload"]["raw_html_s3_key"] == key


def test_crawler_reuses_stored_html_when_queue_delivery_is_retried() -> None:
    crawl_pages = FakeCrawlPagesTable(
        existing={
            "status": "PENDING",
            "raw_html_s3_key": "raw/site-1/crawl-1/page.html",
            "final_url": "https://example.com/",
        }
    )
    s3 = FakeS3Client()
    sqs = FakeSQSClient()

    _service(crawl_pages, s3, sqs).process_message(_message(), attempt=2)

    assert s3.objects == {}
    assert [name for name, _ in crawl_pages.calls] == ["mark_parse_pending"]
    assert len(sqs.messages) == 1


def test_crawler_records_retryable_robots_failure() -> None:
    crawl_pages = FakeCrawlPagesTable(existing={"status": "PENDING"})

    with pytest.raises(RobotsDeniedError):
        _service(
            crawl_pages,
            FakeS3Client(),
            FakeSQSClient(),
            robots_allowed=False,
        ).process_message(_message(), attempt=2)

    failure = crawl_pages.calls[-1]
    assert failure[0] == "record_failure"
    assert failure[1]["attempt"] == 2
    assert not failure[1]["terminal"]


def test_crawler_marks_last_attempt_terminal() -> None:
    crawl_pages = FakeCrawlPagesTable(existing={"status": "PENDING"})

    with pytest.raises(RobotsDeniedError):
        _service(
            crawl_pages,
            FakeS3Client(),
            FakeSQSClient(),
            robots_allowed=False,
        ).process_message(_message(), attempt=5)

    assert crawl_pages.calls[-1][1]["terminal"]


def test_crawler_rejects_a_mismatched_url_hash() -> None:
    message = _message()
    message["payload"]["canonical_url_hash"] = "0" * 64

    with pytest.raises(CrawlMessageError):
        _service(FakeCrawlPagesTable(), FakeS3Client(), FakeSQSClient()).process_message(
            message
        )
