from typing import Any

import pytest

from app.services.nightly_refresh import NightlyRefreshError, NightlyRefreshService


class FakeSitesTable:
    def __init__(self) -> None:
        self.records = [
            {"site_id": "site-one", "root_url": "https://one.example/"},
            {"site_id": "site-two", "root_url": "https://two.example/"},
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return self.records


class FakeCrawlRunsTable:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.created: list[dict[str, Any]] = []

    def get(self, *, site_id: str, crawl_run_id: str) -> dict[str, Any] | None:
        return self.records.get((site_id, crawl_run_id))

    def create(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        self.records[(kwargs["site_id"], kwargs["crawl_run_id"])] = {
            **kwargs,
            "status": "PENDING",
        }


class FakeCrawlPagesTable:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.created: list[dict[str, Any]] = []

    def get(self, *, crawl_run_id: str, canonical_url_hash: str) -> dict[str, Any] | None:
        return self.records.get((crawl_run_id, canonical_url_hash))

    def create(self, **kwargs: Any) -> None:
        self.created.append(kwargs)
        self.records[(kwargs["crawl_run_id"], kwargs["canonical_url_hash"])] = kwargs


class FakeQueue:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def send_json(self, message: dict[str, Any]) -> str:
        self.messages.append(message)
        return "message-id"


def _service() -> tuple[
    NightlyRefreshService,
    FakeCrawlRunsTable,
    FakeCrawlPagesTable,
    FakeQueue,
]:
    runs = FakeCrawlRunsTable()
    pages = FakeCrawlPagesTable()
    queue = FakeQueue()
    return (
        NightlyRefreshService(
            sites=FakeSitesTable(),
            crawl_runs=runs,
            crawl_pages=pages,
            crawl_queue=queue,
        ),
        runs,
        pages,
        queue,
    )


def test_refresh_queues_every_site() -> None:
    service, runs, pages, queue = _service()

    result = service.refresh_all(scheduled_time="2026-09-29T07:00:00Z")

    assert result.discovered_sites == 2
    assert result.queued_sites == 2
    assert result.skipped_sites == 0
    assert len(runs.created) == 2
    assert len(pages.created) == 2
    assert len(queue.messages) == 2
    assert queue.messages[0]["payload"]["crawl_run_id"].startswith("crawl_")


def test_refresh_retry_reuses_pending_run_and_root_page() -> None:
    service, runs, pages, queue = _service()
    scheduled_time = "2026-09-29T07:00:00Z"
    service.refresh_all(scheduled_time=scheduled_time)

    service.refresh_all(scheduled_time=scheduled_time)

    assert len(runs.created) == 2
    assert len(pages.created) == 2
    assert len(queue.messages) == 4
    assert queue.messages[0]["payload"]["crawl_run_id"] == (
        queue.messages[2]["payload"]["crawl_run_id"]
    )


def test_refresh_skips_a_run_that_has_already_started() -> None:
    service, runs, _, queue = _service()
    scheduled_time = "2026-09-29T07:00:00Z"
    service.refresh_all(scheduled_time=scheduled_time)
    first_message = queue.messages[0]
    first_key = ("site-one", first_message["payload"]["crawl_run_id"])
    runs.records[first_key]["status"] = "CRAWLING_AND_PARSING"
    queue.messages.clear()

    result = service.refresh_all(scheduled_time=scheduled_time)

    assert result.queued_sites == 1
    assert result.skipped_sites == 1
    assert queue.messages[0]["payload"]["site_id"] == "site-two"


def test_refresh_requires_the_scheduler_timestamp() -> None:
    service, _, _, _ = _service()

    with pytest.raises(NightlyRefreshError, match="scheduled_time is required"):
        service.refresh_all(scheduled_time="")
