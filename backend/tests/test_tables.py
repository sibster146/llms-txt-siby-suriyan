from typing import Any

from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable


class RecordingDynamoDBClient:
    def __init__(self) -> None:
        self.put_items: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def put_item(self, item: dict[str, Any]) -> None:
        self.put_items.append(item)

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


def test_sites_table_upserts_the_current_crawl() -> None:
    dynamodb = RecordingDynamoDBClient()

    SitesTable(dynamodb).upsert_for_crawl(
        site_id="site-1",
        root_url="https://example.com/",
        crawl_run_id="crawl-1",
        timestamp="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.updates[0]["key"] == {"site_id": "site-1"}
    assert dynamodb.updates[0]["expression_attribute_values"][":crawl_run_id"] == "crawl-1"


def test_user_sites_table_adds_a_mapping() -> None:
    dynamodb = RecordingDynamoDBClient()

    UserSitesTable(dynamodb).add(
        user_id="user-1",
        site_id="site-1",
        created_at="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.updates[0]["key"] == {"user_id": "user-1", "site_id": "site-1"}


def test_crawl_runs_table_creates_initial_counts() -> None:
    dynamodb = RecordingDynamoDBClient()

    CrawlRunsTable(dynamodb).create(
        site_id="site-1",
        crawl_run_id="crawl-1",
        created_at="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.put_items[0]["status"] == "PENDING"
    assert dynamodb.put_items[0]["pending_page_count"] == 1
    assert dynamodb.put_items[0]["discovered_page_count"] == 1


def test_crawl_pages_table_creates_a_page() -> None:
    dynamodb = RecordingDynamoDBClient()

    CrawlPagesTable(dynamodb).create(
        crawl_run_id="crawl-1",
        canonical_url_hash="hash-1",
        site_id="site-1",
        url="https://example.com/docs",
        depth=1,
        parent_url="https://example.com/",
        created_at="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.put_items[0]["canonical_url_hash"] == "hash-1"
    assert dynamodb.put_items[0]["parent_url"] == "https://example.com/"
    assert dynamodb.put_items[0]["status"] == "PENDING"


def test_llms_txt_versions_table_creates_a_version() -> None:
    dynamodb = RecordingDynamoDBClient()

    LlmsTxtVersionsTable(dynamodb).create(
        site_id="site-1",
        version_id="version-1",
        crawl_run_id="crawl-1",
        s3_key="llms-txt/site-1/version-1/llms.txt",
        content_hash="hash-1",
        generated_at="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.put_items[0]["version_id"] == "version-1"
    assert dynamodb.put_items[0]["llms_txt_s3_key"].endswith("/llms.txt")
    assert dynamodb.put_items[0]["status"] == "CURRENT"
