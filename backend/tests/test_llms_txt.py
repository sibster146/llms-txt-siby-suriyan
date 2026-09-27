from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.clients.dynamodb import DynamoDBClientError
from app.clients.sqs import SQSClientError
from app.configs.dependencies import (
    get_crawl_pages_table,
    get_crawl_queue_client,
    get_crawl_runs_table,
    get_current_user_id,
    get_sites_table,
    get_user_sites_table,
)
from app.routes.llms_txt import router


class FakeTable:
    def __init__(
        self,
        fail: bool = False,
        item: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
        items_by_site_id: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.fail = fail
        self.item = item
        self.items = items or []
        self.items_by_site_id = items_by_site_id or {}
        self.calls: list[dict[str, Any]] = []

    def _record(self, operation: str, kwargs: dict[str, Any]) -> None:
        if self.fail:
            raise DynamoDBClientError("unavailable")
        self.calls.append({"operation": operation, **kwargs})

    def upsert_for_crawl(self, **kwargs: Any) -> None:
        self._record("upsert_for_crawl", kwargs)

    def add(self, **kwargs: Any) -> None:
        self._record("add", kwargs)

    def create(self, **kwargs: Any) -> None:
        self._record("create", kwargs)

    def update_status(self, **kwargs: Any) -> None:
        self._record("update_status", kwargs)

    def get(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        if args:
            kwargs["site_id"] = args[0]
        self._record("get", kwargs)
        site_id = kwargs.get("site_id")
        if isinstance(site_id, str) and self.items_by_site_id:
            return self.items_by_site_id.get(site_id)
        return self.item

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        self._record("list_for_user", {"user_id": user_id})
        return self.items


class FakeQueue:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, Any]] = []

    def send_json(self, message: dict[str, Any]) -> str:
        if self.fail:
            raise SQSClientError("unavailable")
        self.messages.append(message)
        return "message-123"


def _test_app(
    sites: FakeTable,
    user_sites: FakeTable,
    crawl_runs: FakeTable,
    crawl_pages: FakeTable,
    *,
    authenticated: bool = True,
    crawl_queue: FakeQueue | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_sites_table] = lambda: sites
    app.dependency_overrides[get_user_sites_table] = lambda: user_sites
    app.dependency_overrides[get_crawl_runs_table] = lambda: crawl_runs
    app.dependency_overrides[get_crawl_pages_table] = lambda: crawl_pages
    app.dependency_overrides[get_crawl_queue_client] = lambda: crawl_queue or FakeQueue()
    if authenticated:
        app.dependency_overrides[get_current_user_id] = lambda: "user-123"
    return app


def test_create_llms_txt_persists_site_mapping_and_crawl() -> None:
    sites = FakeTable()
    user_sites = FakeTable()
    crawl_runs = FakeTable()
    crawl_pages = FakeTable()
    crawl_queue = FakeQueue()

    app = _test_app(
        sites,
        user_sites,
        crawl_runs,
        crawl_pages,
        crawl_queue=crawl_queue,
    )
    with TestClient(app) as client:
        response = client.post(
            "/llms-txt",
            json={"url": "HTTPS://Example.com:443/docs#intro"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["url"] == "https://example.com/docs"
    assert body["site_id"].startswith("site_")
    assert body["crawl_run_id"].startswith("crawl_")

    assert sites.calls[0]["site_id"] == body["site_id"]
    assert user_sites.calls[0] == {
        "operation": "add",
        "user_id": "user-123",
        "site_id": body["site_id"],
        "created_at": user_sites.calls[0]["created_at"],
    }
    assert crawl_runs.calls[0]["site_id"] == body["site_id"]
    assert crawl_runs.calls[0]["crawl_run_id"] == body["crawl_run_id"]
    assert crawl_pages.calls[0]["url"] == "https://example.com/docs"
    assert crawl_pages.calls[0]["depth"] == 0
    assert crawl_queue.messages == [
        {
            "action": "crawl_url",
            "payload": {
                "site_id": body["site_id"],
                "crawl_run_id": body["crawl_run_id"],
                "url": "https://example.com/docs",
                "canonical_url_hash": body["site_id"].removeprefix("site_"),
                "depth": 0,
            },
        }
    ]


def test_create_llms_txt_rejects_invalid_url() -> None:
    dynamodb = FakeTable()

    with TestClient(_test_app(dynamodb, dynamodb, dynamodb, dynamodb)) as client:
        response = client.post(
            "/llms-txt",
            json={"url": "not-a-url"},
        )

    assert response.status_code == 422
    assert dynamodb.calls == []


def test_create_llms_txt_returns_bad_gateway_when_dynamodb_fails() -> None:
    dynamodb = FakeTable(fail=True)
    crawl_queue = FakeQueue()

    app = _test_app(
        dynamodb,
        dynamodb,
        dynamodb,
        dynamodb,
        crawl_queue=crawl_queue,
    )
    with TestClient(app) as client:
        response = client.post(
            "/llms-txt",
            json={"url": "https://example.com"},
        )

    assert response.status_code == 502
    assert response.json() == {"detail": "The crawl request could not be saved."}
    assert crawl_queue.messages == []


def test_create_llms_txt_rejects_request_user_id() -> None:
    dynamodb = FakeTable()

    with TestClient(_test_app(dynamodb, dynamodb, dynamodb, dynamodb)) as client:
        response = client.post(
            "/llms-txt",
            json={"user_id": "another-user", "url": "https://example.com"},
        )

    assert response.status_code == 422
    assert dynamodb.calls == []


def test_create_llms_txt_requires_authentication() -> None:
    dynamodb = FakeTable()
    app = _test_app(
        dynamodb,
        dynamodb,
        dynamodb,
        dynamodb,
        authenticated=False,
    )

    with TestClient(app) as client:
        response = client.post("/llms-txt", json={"url": "https://example.com"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert dynamodb.calls == []


def test_create_llms_txt_marks_run_failed_when_queueing_fails() -> None:
    sites = FakeTable()
    user_sites = FakeTable()
    crawl_runs = FakeTable()
    crawl_pages = FakeTable()
    app = _test_app(
        sites,
        user_sites,
        crawl_runs,
        crawl_pages,
        crawl_queue=FakeQueue(fail=True),
    )

    with TestClient(app) as client:
        response = client.post("/llms-txt", json={"url": "https://example.com"})

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The crawl request was saved but could not be queued."
    }
    assert crawl_runs.calls[-1]["operation"] == "update_status"
    assert crawl_runs.calls[-1]["crawl_status"] == "FAILED"


def test_get_crawl_status_returns_owned_crawl() -> None:
    user_sites = FakeTable(item={"user_id": "user-123", "site_id": "site-1"})
    crawl_runs = FakeTable(
        item={
            "site_id": "site-1",
            "crawl_run_id": "crawl-1",
            "status": "WORKING",
            "pending_page_count": 2,
            "discovered_page_count": 4,
            "completed_page_count": 1,
            "failed_page_count": 1,
            "created_at": "2026-09-27T01:00:00+00:00",
            "updated_at": "2026-09-27T01:01:00+00:00",
        }
    )
    app = _test_app(FakeTable(), user_sites, crawl_runs, FakeTable())

    with TestClient(app) as client:
        response = client.get("/llms-txt/site-1/crawls/crawl-1")

    assert response.status_code == 200
    assert response.json()["status"] == "WORKING"
    assert response.json()["discovered_page_count"] == 4
    assert user_sites.calls[0]["user_id"] == "user-123"


def test_get_crawl_status_hides_crawls_not_owned_by_user() -> None:
    user_sites = FakeTable(item=None)
    crawl_runs = FakeTable(
        item={"site_id": "site-1", "crawl_run_id": "crawl-1", "status": "PENDING"}
    )
    app = _test_app(FakeTable(), user_sites, crawl_runs, FakeTable())

    with TestClient(app) as client:
        response = client.get("/llms-txt/site-1/crawls/crawl-1")

    assert response.status_code == 404
    assert crawl_runs.calls == []


def test_list_user_sites_loads_mapped_sites_most_recent_first() -> None:
    user_sites = FakeTable(
        items=[
            {"user_id": "user-123", "site_id": "site-1"},
            {"user_id": "user-123", "site_id": "site-2"},
        ]
    )
    sites = FakeTable(
        items_by_site_id={
            "site-1": {
                "site_id": "site-1",
                "root_url": "https://one.example/",
                "last_crawl_run_id": "crawl-1",
                "created_at": "2026-09-26T12:00:00+00:00",
                "updated_at": "2026-09-26T12:00:00+00:00",
                "modified_at": "2026-09-27T13:00:00+00:00",
            },
            "site-2": {
                "site_id": "site-2",
                "root_url": "https://two.example/",
                "last_crawl_run_id": "crawl-2",
                "created_at": "2026-09-27T12:00:00+00:00",
                "updated_at": "2026-09-27T12:00:00+00:00",
                "modified_at": "2026-09-27T12:00:00+00:00",
            },
        }
    )
    app = _test_app(sites, user_sites, FakeTable(), FakeTable())

    with TestClient(app) as client:
        response = client.get("/llms-txt/sites")

    assert response.status_code == 200
    assert [site["site_id"] for site in response.json()] == ["site-1", "site-2"]
    assert response.json()[0]["modified_at"] == "2026-09-27T13:00:00+00:00"
    assert user_sites.calls[0] == {
        "operation": "list_for_user",
        "user_id": "user-123",
    }
