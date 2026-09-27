from typing import Any

from app.clients.dynamodb import DynamoDBClient


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
        item: dict[str, Any] = {
            "crawl_run_id": crawl_run_id,
            "canonical_url_hash": canonical_url_hash,
            "site_id": site_id,
            "url": url,
            "canonical_url": url,
            "depth": depth,
            "status": "PENDING",
            "created_at": created_at,
        }
        if parent_url is not None:
            item["parent_url"] = parent_url
        self.dynamodb.put_item(item)

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
            ":crawled_at": crawled_at,
        }
        update_parts = [
            "#status = :status",
            "raw_html_s3_key = :raw_html_s3_key",
            "final_url = :final_url",
            "http_status = :http_status",
            "content_type = :content_type",
            "content_length = :content_length",
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
        self.update_status(
            crawl_run_id=crawl_run_id,
            canonical_url_hash=canonical_url_hash,
            crawl_status="PARSE_PENDING",
            updated_at=updated_at,
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
    ) -> None:
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
        )
