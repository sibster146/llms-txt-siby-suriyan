from typing import Any

import pytest
from boto3.dynamodb.conditions import LessThanEquals

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


class ConditionalPageClient(RecordingDynamoDBClient):
    """Apply the status conditions against a page to simulate interleaved workers."""

    def __init__(self, status: str) -> None:
        super().__init__()
        self.page = {"status": status, "parse_started_at": "attempt-1"}

    def matches(self, condition: Any) -> bool:
        expr = condition.get_expression()
        values = expr["values"]
        operator = expr["operator"]
        if operator == "AND":
            return all(self.matches(value) for value in values)
        if operator == "OR":
            return any(self.matches(value) for value in values)
        name = values[0].name
        if operator == "attribute_not_exists":
            return name not in self.page
        current = self.page.get(name)
        if operator == "=":
            return current == values[1]
        if operator == "IN":
            return current in values[1]
        if operator == "<":
            return current is not None and current < values[1]
        raise AssertionError(f"Unsupported condition: {operator}")

    def update_item(self, **kwargs: Any) -> None:
        if not self.matches(kwargs["condition_expression"]):
            raise DynamoDBConditionNotMetError("page already advanced")
        super().update_item(**kwargs)
        values = kwargs["expression_attribute_values"]
        if ":status" in values:
            self.page["status"] = values[":status"]
        if ":parsing" in values:
            self.page["status"] = values[":parsing"]
            self.page["parse_started_at"] = values[":claimed_at"]
            self.page["parse_lease_expires_at"] = values[":lease_expires_at"]
        elif "parse_lease_expires_at = :updated_at" in kwargs["update_expression"]:
            self.page["parse_lease_expires_at"] = values[":updated_at"]


@pytest.mark.parametrize("status", ["PARSING", "PARSED", "FAILED"])
def test_late_crawler_cannot_reset_parser_owned_or_terminal_page(status: str) -> None:
    client = ConditionalPageClient(status)
    table = CrawlPagesTable(client)
    key = {"crawl_run_id": "run", "canonical_url_hash": "hash"}
    table.mark_queued(**key, updated_at="late")
    assert not table.mark_parse_pending(**key, updated_at="late")
    with pytest.raises(DynamoDBConditionNotMetError):
        table.mark_crawling(**key, updated_at="late")
    with pytest.raises(DynamoDBConditionNotMetError):
        table.mark_crawled(
            **key,
            raw_html_s3_key="raw/key",
            final_url="https://example.com",
            http_status=200,
            content_type="text/html",
            content_length=10,
            raw_html_hash="hash",
            html_unchanged=False,
            crawled_at="late",
            etag=None,
            last_modified=None,
        )
    for terminal in (False, True):
        assert not table.record_failure(
            **key,
            error_message="late failure",
            attempt=2,
            terminal=terminal,
            updated_at="late",
        )
    assert client.page["status"] == status
    assert not client.updates


def test_parser_completion_cannot_be_repeated_or_reset_by_failure() -> None:
    client = ConditionalPageClient("PARSING")
    table = CrawlPagesTable(client)
    key = {"crawl_run_id": "run", "canonical_url_hash": "hash"}
    completion = dict(
        **key, parsed_content_s3_key="parsed/key", parsed_at="done", claimed_at="attempt-1"
    )
    table.mark_parsed(**completion)
    with pytest.raises(DynamoDBConditionNotMetError):
        table.mark_parsed(**completion)
    with pytest.raises(DynamoDBConditionNotMetError):
        table.record_parse_failure(
            **key,
            error_message="late error",
            attempt=1,
            terminal=False,
            updated_at="later",
            claimed_at="attempt-1",
        )
    assert client.page["status"] == "PARSED"


def test_parser_retry_stays_parsing_and_fences_previous_attempt() -> None:
    client = ConditionalPageClient("PARSING")
    table = CrawlPagesTable(client)
    key = {"crawl_run_id": "run", "canonical_url_hash": "hash"}
    table.record_parse_failure(
        **key,
        error_message="retryable",
        attempt=1,
        terminal=False,
        updated_at="2026-09-29T10:00:00+00:00",
        claimed_at="attempt-1",
    )
    assert client.page["status"] == "PARSING"
    assert table.claim_parsing(
        **key,
        claimed_at="2026-09-29T10:00:30+00:00",
        lease_expires_at="2026-09-29T10:02:30+00:00",
    )
    with pytest.raises(DynamoDBConditionNotMetError):
        table.mark_parsed(
            **key,
            parsed_content_s3_key="key",
            parsed_at="late",
            claimed_at="attempt-1",
        )


def test_parser_cannot_claim_crawled_page_until_parse_pending() -> None:
    client = ConditionalPageClient("CRAWLED")
    table = CrawlPagesTable(client)
    key = {"crawl_run_id": "run", "canonical_url_hash": "hash"}
    claim = dict(**key, claimed_at="start", lease_expires_at="until")
    assert not table.claim_parsing(**claim)
    assert table.mark_parse_pending(**key, updated_at="queued")
    assert table.claim_parsing(**claim)
    assert not table.mark_parse_pending(**key, updated_at="late")
    assert not table.claim_parsing(**claim)


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
    assert "if_not_exists(last_crawl_run_id" in dynamodb.updates[0]["update_expression"]


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
        crawl_run_id="crawl-1",
        timestamp="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.updates[0]["key"] == {"user_id": "user-1", "site_id": "site-1"}
    assert dynamodb.updates[0]["expression_attribute_values"][":crawl_run_id"] == ("crawl-1")


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
    assert "force" not in dynamodb.put_items[0]


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


def test_crawl_pages_table_claims_parsing_atomically() -> None:
    dynamodb = RecordingDynamoDBClient()

    claimed = CrawlPagesTable(dynamodb).claim_parsing(
        crawl_run_id="crawl-1",
        canonical_url_hash="hash-1",
        claimed_at="2026-09-27T22:00:00+00:00",
        lease_expires_at="2026-09-27T22:02:00+00:00",
    )

    assert claimed
    assert dynamodb.updates[0]["expression_attribute_values"][":parsing"] == "PARSING"
    assert dynamodb.updates[0]["condition_expression"] is not None


def test_crawl_runs_table_records_parser_progress() -> None:
    dynamodb = RecordingDynamoDBClient()

    CrawlRunsTable(dynamodb).record_parsed_page(
        site_id="site-1",
        crawl_run_id="crawl-1",
        updated_at="2026-09-27T02:00:00+00:00",
    )

    values = dynamodb.updates[0]["expression_attribute_values"]
    assert values[":pending"] == -1
    assert values[":completed"] == 1


def test_crawl_runs_table_reserves_discovery_capacity_atomically() -> None:
    dynamodb = RecordingDynamoDBClient()

    reserved = CrawlRunsTable(dynamodb).reserve_discovered_page(
        site_id="site-1",
        crawl_run_id="crawl-1",
        max_discovered_pages=1000,
        updated_at="2026-09-27T02:00:00+00:00",
    )

    assert reserved
    values = dynamodb.updates[0]["expression_attribute_values"]
    assert values[":one"] == 1
    assert ":max_discovered_pages" not in values
    assert dynamodb.updates[0]["condition_expression"] is not None


def test_crawl_runs_table_rejects_discovery_at_capacity() -> None:
    class FullCrawlDynamoDBClient(RecordingDynamoDBClient):
        def update_item(self, **kwargs: Any) -> None:
            raise DynamoDBConditionNotMetError("crawl is at capacity")

    reserved = CrawlRunsTable(FullCrawlDynamoDBClient()).reserve_discovered_page(
        site_id="site-1",
        crawl_run_id="crawl-1",
        max_discovered_pages=1000,
        updated_at="2026-09-27T02:00:00+00:00",
    )

    assert not reserved


def test_crawl_runs_table_records_terminal_crawl_failure() -> None:
    dynamodb = RecordingDynamoDBClient()

    CrawlRunsTable(dynamodb).record_failed_page(
        site_id="site-1",
        crawl_run_id="crawl-1",
        updated_at="2026-09-27T02:00:00+00:00",
    )

    values = dynamodb.updates[0]["expression_attribute_values"]
    assert values[":pending"] == -1
    assert values[":failed"] == 1


def test_crawl_runs_table_claims_generation_atomically() -> None:
    dynamodb = RecordingDynamoDBClient()

    claimed = CrawlRunsTable(dynamodb).claim_generation(
        site_id="site-1",
        crawl_run_id="crawl-1",
        updated_at="2026-09-27T03:00:00+00:00",
    )

    assert claimed
    assert dynamodb.updates[0]["expression_attribute_values"][":status"] == "GENERATING"
    condition = dynamodb.updates[0]["condition_expression"]
    assert any(isinstance(value, LessThanEquals) for value in condition.get_expression()["values"])


def test_crawl_runs_table_rejects_a_duplicate_generation_claim() -> None:
    class AlreadyClaimedDynamoDBClient(RecordingDynamoDBClient):
        def update_item(self, **kwargs: Any) -> None:
            raise DynamoDBConditionNotMetError("already claimed")

    claimed = CrawlRunsTable(AlreadyClaimedDynamoDBClient()).claim_generation(
        site_id="site-1",
        crawl_run_id="crawl-1",
        updated_at="2026-09-27T03:00:00+00:00",
    )

    assert not claimed


def test_llms_txt_versions_table_creates_a_version() -> None:
    dynamodb = RecordingDynamoDBClient()

    LlmsTxtVersionsTable(dynamodb).create(
        site_id="site-1",
        version_id="version-1",
        crawl_run_id="crawl-1",
        s3_key="llms-txt/site-1/version-1/llms.txt",
        content_hash="hash-1",
        crawl_content_hash="crawl-hash-1",
        generated_at="2026-09-27T00:00:00+00:00",
    )

    assert dynamodb.put_items[0]["version_id"] == "version-1"
    assert dynamodb.put_items[0]["llms_txt_s3_key"].endswith("/llms.txt")
    assert dynamodb.put_items[0]["crawl_content_hash"] == "crawl-hash-1"
    assert dynamodb.put_items[0]["status"] == "CURRENT"
