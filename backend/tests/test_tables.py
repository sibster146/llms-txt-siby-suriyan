from typing import Any

from app.clients.dynamodb import DynamoDBConditionNotMetError
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable


class RecordingDynamoDBClient:
    def __init__(self) -> None:
        self.put_items: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []
        self.queries: list[dict[str, Any]] = []
        self.query_results: list[dict[str, Any]] = []

    def put_item(
        self,
        item: dict[str, Any],
        condition_expression: Any = None,
    ) -> None:
        self.put_items.append(item)

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def query(self, key_condition: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.queries.append({"key_condition": key_condition, **kwargs})
        return self.query_results


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
    assert "if_not_exists(last_crawl_run_id" in dynamodb.updates[0][
        "update_expression"
    ]


def test_sites_table_marks_the_latest_changed_crawl() -> None:
    dynamodb = RecordingDynamoDBClient()

    SitesTable(dynamodb).mark_content_changed(
        site_id="site-1",
        crawl_run_id="crawl-2",
        modified_at="2026-09-27T01:00:00+00:00",
    )

    assert dynamodb.updates[0]["expression_attribute_values"][":crawl_run_id"] == "crawl-2"
    assert dynamodb.updates[0]["expression_attribute_values"][":modified_at"] == (
        "2026-09-27T01:00:00+00:00"
    )
    assert "updated_at" not in dynamodb.updates[0]["update_expression"]
    assert dynamodb.updates[0]["condition_expression"] is not None


def test_sites_table_ignores_an_older_content_change() -> None:
    class StaleWriteDynamoDBClient(RecordingDynamoDBClient):
        def update_item(self, **kwargs: Any) -> None:
            raise DynamoDBConditionNotMetError("stale timestamp")

    SitesTable(StaleWriteDynamoDBClient()).mark_content_changed(
        site_id="site-1",
        crawl_run_id="crawl-old",
        modified_at="2026-09-27T00:00:00+00:00",
    )


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
    assert dynamodb.put_items[0]["site_url_key"] == "site-1#hash-1"
    assert dynamodb.put_items[0]["parent_url"] == "https://example.com/"
    assert dynamodb.put_items[0]["status"] == "PENDING"


def test_crawl_pages_table_loads_latest_crawled_version() -> None:
    dynamodb = RecordingDynamoDBClient()
    dynamodb.query_results = [{"crawl_run_id": "crawl-2"}]

    page = CrawlPagesTable(dynamodb).get_latest_crawled(
        site_id="site-1",
        canonical_url_hash="hash-1",
    )

    assert page == {"crawl_run_id": "crawl-2"}
    assert dynamodb.queries[0]["IndexName"] == "site_url_crawled_at_index"
    assert dynamodb.queries[0]["ScanIndexForward"] is False
    assert dynamodb.queries[0]["Limit"] == 1


def test_crawl_runs_table_records_parser_progress() -> None:
    dynamodb = RecordingDynamoDBClient()

    CrawlRunsTable(dynamodb).record_parsed_page(
        site_id="site-1",
        crawl_run_id="crawl-1",
        discovered_page_count=3,
        updated_at="2026-09-27T02:00:00+00:00",
    )

    values = dynamodb.updates[0]["expression_attribute_values"]
    assert values[":pending_delta"] == 2
    assert values[":discovered"] == 3
    assert values[":completed"] == 1


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
