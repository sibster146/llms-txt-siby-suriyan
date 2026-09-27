from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError

LATEST_PAGE_INDEX = "site_url_crawled_at_index"


class CrawlPagesTable:
    """Persistence operations for pages discovered during a crawl."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    def create(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        site_id: str,
        url: str,
        depth: int,
        created_at: str,
        parent_url: str | None = None,
    ) -> None:
        self.dynamodb.put_item(
            self._new_page_item(
                crawl_run_id=crawl_run_id,
                canonical_url_hash=canonical_url_hash,
                site_id=site_id,
                url=url,
                depth=depth,
                created_at=created_at,
                parent_url=parent_url,
                status="PENDING",
            )
        )

    def create_if_absent(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        site_id: str,
        url: str,
        depth: int,
        created_at: str,
        parent_url: str,
    ) -> bool:
        try:
            self.dynamodb.put_item(
                self._new_page_item(
                    crawl_run_id=crawl_run_id,
                    canonical_url_hash=canonical_url_hash,
                    site_id=site_id,
                    url=url,
                    depth=depth,
                    created_at=created_at,
                    parent_url=parent_url,
                    status="DISCOVERED",
                ),
                condition_expression=(
                    Attr("crawl_run_id").not_exists() & Attr("canonical_url_hash").not_exists()
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    @staticmethod
    def _new_page_item(
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        site_id: str,
        url: str,
        depth: int,
        created_at: str,
        parent_url: str | None,
        status: str,
    ) -> dict[str, Any]:
        item: dict[str, Any] = {
            "crawl_run_id": crawl_run_id,
            "canonical_url_hash": canonical_url_hash,
            "site_id": site_id,
            "site_url_key": f"{site_id}#{canonical_url_hash}",
            "url": url,
            "canonical_url": url,
            "depth": depth,
            "status": status,
            "created_at": created_at,
        }
        if parent_url is not None:
            item["parent_url"] = parent_url
        return item

    def get(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
    ) -> dict[str, Any] | None:
        return self.dynamodb.get_item(
            key={
                "crawl_run_id": crawl_run_id,
                "canonical_url_hash": canonical_url_hash,
            }
        )

    def get_latest_crawled(
        self,
        *,
        site_id: str,
        canonical_url_hash: str,
    ) -> dict[str, Any] | None:
        pages = self.dynamodb.query(
            Key("site_url_key").eq(f"{site_id}#{canonical_url_hash}"),
            IndexName=LATEST_PAGE_INDEX,
            ScanIndexForward=False,
            Limit=1,
        )
        return pages[0] if pages else None

    def list_for_run(self, crawl_run_id: str) -> list[dict[str, Any]]:
        return self.dynamodb.query(Key("crawl_run_id").eq(crawl_run_id))

    def update_status(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        crawl_status: str,
        updated_at: str,
    ) -> None:
        self.dynamodb.update_item(
            key={
                "crawl_run_id": crawl_run_id,
                "canonical_url_hash": canonical_url_hash,
            },
            update_expression="SET #status = :status, updated_at = :updated_at",
            expression_attribute_names={"#status": "status"},
            expression_attribute_values={
                ":status": crawl_status,
                ":updated_at": updated_at,
            },
        )

    def mark_crawling(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        updated_at: str,
    ) -> None:
        self.update_status(
            crawl_run_id=crawl_run_id,
            canonical_url_hash=canonical_url_hash,
            crawl_status="CRAWLING",
            updated_at=updated_at,
        )

    def mark_crawled(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        raw_html_s3_key: str,
        final_url: str,
        http_status: int,
        content_type: str,
        content_length: int,
        raw_html_hash: str,
        html_unchanged: bool,
        crawled_at: str,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        values: dict[str, Any] = {
            ":status": "CRAWLED",
            ":raw_html_s3_key": raw_html_s3_key,
            ":final_url": final_url,
            ":http_status": http_status,
            ":content_type": content_type,
            ":content_length": content_length,
            ":raw_html_hash": raw_html_hash,
            ":html_unchanged": html_unchanged,
            ":crawled_at": crawled_at,
        }
        update_parts = [
            "#status = :status",
            "raw_html_s3_key = :raw_html_s3_key",
            "final_url = :final_url",
            "http_status = :http_status",
            "content_type = :content_type",
            "content_length = :content_length",
            "raw_html_hash = :raw_html_hash",
            "html_unchanged = :html_unchanged",
            "crawled_at = :crawled_at",
        ]
        if etag:
            values[":etag"] = etag
            update_parts.append("etag = :etag")
        if last_modified:
            values[":last_modified"] = last_modified
            update_parts.append("last_modified = :last_modified")

        self.dynamodb.update_item(
            key={
                "crawl_run_id": crawl_run_id,
                "canonical_url_hash": canonical_url_hash,
            },
            update_expression=f"SET {', '.join(update_parts)}",
            expression_attribute_names={"#status": "status"},
            expression_attribute_values=values,
        )

    def mark_parse_pending(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        updated_at: str,
    ) -> None:
        try:
            self.dynamodb.update_item(
                key={
                    "crawl_run_id": crawl_run_id,
                    "canonical_url_hash": canonical_url_hash,
                },
                update_expression="SET #status = :status, updated_at = :updated_at",
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": "PARSE_PENDING",
                    ":updated_at": updated_at,
                },
                condition_expression=(
                    Attr("status").not_exists()
                    | (Attr("status").ne("PARSED") & Attr("status").ne("FAILED"))
                ),
            )
        except DynamoDBConditionNotMetError:
            return

    def claim_parsing(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        started_at: str,
        stale_before: str,
    ) -> bool:
        try:
            self.dynamodb.update_item(
                key={
                    "crawl_run_id": crawl_run_id,
                    "canonical_url_hash": canonical_url_hash,
                },
                update_expression=(
                    "SET #status = :parsing, parse_started_at = :started_at, "
                    "updated_at = :started_at"
                ),
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":parsing": "PARSING",
                    ":started_at": started_at,
                },
                condition_expression=(
                    Attr("status").is_in(["CRAWLED", "PARSE_PENDING"])
                    | (Attr("status").eq("PARSING") & Attr("parse_started_at").lt(stale_before))
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def mark_queued(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        updated_at: str,
    ) -> None:
        self.update_status(
            crawl_run_id=crawl_run_id,
            canonical_url_hash=canonical_url_hash,
            crawl_status="PENDING",
            updated_at=updated_at,
        )

    def mark_parsed(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        parsed_content_s3_key: str,
        parsed_at: str,
    ) -> None:
        self.dynamodb.update_item(
            key={
                "crawl_run_id": crawl_run_id,
                "canonical_url_hash": canonical_url_hash,
            },
            update_expression=(
                "SET #status = :status, parsed_content_s3_key = :parsed_key, "
                "parsed_at = :parsed_at, updated_at = :updated_at"
            ),
            expression_attribute_names={"#status": "status"},
            expression_attribute_values={
                ":status": "PARSED",
                ":parsed_key": parsed_content_s3_key,
                ":parsed_at": parsed_at,
                ":updated_at": parsed_at,
            },
        )

    def record_parse_failure(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        error_message: str,
        attempt: int,
        terminal: bool,
        updated_at: str,
    ) -> None:
        self.dynamodb.update_item(
            key={
                "crawl_run_id": crawl_run_id,
                "canonical_url_hash": canonical_url_hash,
            },
            update_expression=(
                "SET #status = :status, last_error = :last_error, "
                "parse_attempt = :attempt, updated_at = :updated_at"
            ),
            expression_attribute_names={"#status": "status"},
            expression_attribute_values={
                ":status": "FAILED" if terminal else "PARSE_PENDING",
                ":last_error": error_message[:1000],
                ":attempt": attempt,
                ":updated_at": updated_at,
            },
        )

    def record_failure(
        self,
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        error_message: str,
        attempt: int,
        terminal: bool,
        updated_at: str,
    ) -> bool:
        try:
            self.dynamodb.update_item(
                key={
                    "crawl_run_id": crawl_run_id,
                    "canonical_url_hash": canonical_url_hash,
                },
                update_expression=(
                    "SET #status = :status, last_error = :last_error, "
                    "crawl_attempt = :attempt, updated_at = :updated_at"
                ),
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": "FAILED" if terminal else "PENDING",
                    ":last_error": error_message[:1000],
                    ":attempt": attempt,
                    ":updated_at": updated_at,
                },
                condition_expression=(Attr("status").ne("FAILED") if terminal else None),
            )
        except DynamoDBConditionNotMetError:
            return False
        return terminal
