import contextlib
from typing import Any

from boto3.dynamodb.conditions import Attr, Key

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError

TERMINAL_PAGE_STATUSES = {"COMPLETED", "FAILED"}
LATEST_PAGE_INDEX = "site_url_crawled_at_index"


class CrawlPagesTable:
    """Page state and fenced writes. No persisted aggregate counters."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    @staticmethod
    def new_item(
        *,
        crawl_run_id: str,
        canonical_url_hash: str,
        site_id: str,
        url: str,
        root_url: str,
        depth: int,
        created_at: str,
        parent_url: str | None = None,
    ) -> dict[str, Any]:
        item = dict(
            crawl_run_id=crawl_run_id,
            canonical_url_hash=canonical_url_hash,
            site_id=site_id,
            site_url_key=f"{site_id}#{canonical_url_hash}",
            url=url,
            root_url=root_url,
            depth=depth,
            status="QUEUED",
            created_at=created_at,
            updated_at=created_at,
            attempt_count=0,
            dispatch_pending=True,
        )
        if parent_url is not None:
            item["parent_url"] = parent_url
        return item

    @staticmethod
    def key(page: dict) -> dict:
        return {k: page[k] for k in ("crawl_run_id", "canonical_url_hash")}

    def initialize_run(self, run: dict, root: dict, runs_table_name: str, site_write: dict) -> None:
        self.dynamodb.transact_write(
            [
                site_write,
                {
                    "Put": {
                        "TableName": runs_table_name,
                        "Item": run,
                        "ConditionExpression": "attribute_not_exists(crawl_run_id)",
                    }
                },
                {
                    "Put": {
                        "TableName": self.dynamodb.table_name,
                        "Item": root,
                        "ConditionExpression": "attribute_not_exists(crawl_run_id)",
                    }
                },
            ]
        )

    def get(self, *, crawl_run_id: str, canonical_url_hash: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(
            key=dict(crawl_run_id=crawl_run_id, canonical_url_hash=canonical_url_hash),
            consistent_read=True,
        )

    def list_for_run(self, crawl_run_id: str) -> list[dict[str, Any]]:
        return self.dynamodb.query(Key("crawl_run_id").eq(crawl_run_id), ConsistentRead=True)

    def get_latest_crawled(self, *, site_id: str, canonical_url_hash: str) -> dict | None:
        pages = self.dynamodb.query(
            Key("site_url_key").eq(f"{site_id}#{canonical_url_hash}"),
            IndexName=LATEST_PAGE_INDEX,
            ScanIndexForward=False,
            Limit=1,
        )
        return pages[0] if pages else None

    def counts_for_run(self, crawl_run_id: str) -> dict[str, int]:
        pages = self.list_for_run(crawl_run_id)
        complete = sum(p["status"] == "COMPLETED" for p in pages)
        failed = sum(p["status"] == "FAILED" for p in pages)
        return dict(
            discovered_page_count=len(pages),
            completed_page_count=complete,
            failed_page_count=failed,
            pending_page_count=len(pages) - complete - failed,
        )

    def claim(
        self,
        page: dict,
        *,
        runs_table_name: str,
        token: str,
        now: str,
        expires_at: str,
        max_attempts: int,
    ) -> bool:
        attempts = int(page.get("attempt_count", 0))
        if attempts >= max_attempts and not page.get("parsed_content_s3_key"):
            return False
        try:
            self.dynamodb.transact_write(
                [
                    {
                        "Update": {
                            "TableName": runs_table_name,
                            "Key": {
                                "site_id": page["site_id"],
                                "crawl_run_id": page["crawl_run_id"],
                            },
                            "UpdateExpression": "SET #s = :working, updated_at = :now",
                            "ConditionExpression": "#s IN (:pending, :working)",
                            "ExpressionAttributeNames": {"#s": "status"},
                            "ExpressionAttributeValues": {
                                ":pending": "PENDING",
                                ":working": "CRAWLING_AND_PARSING",
                                ":now": now,
                            },
                        }
                    },
                    {
                        "Update": {
                            "TableName": self.dynamodb.table_name,
                            "Key": self.key(page),
                            "UpdateExpression": (
                                "SET #s = :working, worker_token = :token, "
                                "lease_expires_at = :expiry, "
                                "attempt_count = :next, updated_at = :now, dispatch_pending = :no "
                                "REMOVE retry_after"
                            ),
                            "ConditionExpression": (
                                "site_id = :site AND attempt_count = :previous AND "
                                "(#s = :queued OR (#s = :working AND lease_expires_at <= :now)) "
                                "AND (attribute_not_exists(retry_after) OR retry_after <= :now)"
                            ),
                            "ExpressionAttributeNames": {"#s": "status"},
                            "ExpressionAttributeValues": {
                                ":site": page["site_id"],
                                ":queued": "QUEUED",
                                ":working": "CRAWLING_AND_PARSING",
                                ":token": token,
                                ":expiry": expires_at,
                                ":next": attempts + (0 if page.get("parsed_content_s3_key") else 1),
                                ":previous": attempts,
                                ":now": now,
                                ":no": False,
                            },
                        }
                    },
                ]
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    @staticmethod
    def ownership(token: str, now: str) -> Any:
        return (
            Attr("status").eq("CRAWLING_AND_PARSING")
            & Attr("worker_token").eq(token)
            & Attr("lease_expires_at").gt(now)
        )

    def save_result(self, page: dict, *, token: str, now: str, result: dict) -> None:
        names = {f"#f{i}": k for i, k in enumerate(result)}
        values = {f":field{i}": v for i, v in enumerate(result.values())}
        self.dynamodb.update_item(
            key=self.key(page),
            update_expression="SET " + ", ".join(f"#f{i} = :field{i}" for i in range(len(result))),
            expression_attribute_names=names,
            expression_attribute_values=values,
            condition_expression=self.ownership(token, now),
        )

    def finish(self, page: dict, *, token: str, now: str, error: str | None = None) -> None:
        self.dynamodb.update_item(
            key=self.key(page),
            update_expression=(
                "SET #s = :status, updated_at = :now, last_error = :error "
                "REMOVE worker_token, lease_expires_at, retry_after, "
                "dispatch_pending, dispatch_after"
            ),
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":status": "FAILED" if error else "COMPLETED",
                ":now": now,
                ":error": (error or "")[:1000],
            },
            condition_expression=self.ownership(token, now),
        )

    def retry(self, page: dict, *, token: str, now: str, retry_after: str, error: str) -> None:
        self.dynamodb.update_item(
            key=self.key(page),
            update_expression=(
                "SET lease_expires_at = :now, retry_after = :retry, last_error = :error, "
                "dispatch_pending = :yes, updated_at = :now REMOVE worker_token, dispatch_after"
            ),
            expression_attribute_values={
                ":now": now,
                ":retry": retry_after,
                ":error": error[:1000],
                ":yes": True,
            },
            condition_expression=self.ownership(token, now),
        )

    def fail_abandoned(self, page: dict, *, now: str, error: str) -> bool:
        try:
            self.dynamodb.update_item(
                key=self.key(page),
                update_expression=(
                    "SET #s = :failed, last_error = :error, updated_at = :now "
                    "REMOVE worker_token, lease_expires_at, retry_after, "
                    "dispatch_pending, dispatch_after"
                ),
                expression_attribute_names={"#s": "status"},
                expression_attribute_values={
                    ":failed": "FAILED",
                    ":error": error[:1000],
                    ":now": now,
                },
                condition_expression=(
                    Attr("site_id").eq(page["site_id"])
                    & Attr("attempt_count").eq(page["attempt_count"])
                    & Attr("parsed_content_s3_key").not_exists()
                    & (
                        (Attr("status").eq("QUEUED"))
                        | (
                            Attr("status").eq("CRAWLING_AND_PARSING")
                            & Attr("lease_expires_at").lte(now)
                        )
                    )
                    & (Attr("retry_after").not_exists() | Attr("retry_after").lte(now))
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def mark_sent(self, page: dict, *, dispatch_after: str) -> None:
        with contextlib.suppress(DynamoDBConditionNotMetError):
            self.dynamodb.update_item(
                key=self.key(page),
                update_expression="SET dispatch_pending = :no, dispatch_after = :after",
                expression_attribute_values={":no": False, ":after": dispatch_after},
                condition_expression=(
                    Attr("attempt_count").eq(page["attempt_count"])
                    & Attr("status").is_in(["QUEUED", "CRAWLING_AND_PARSING"])
                ),
            )

    def register_children(
        self,
        parent: dict,
        children: list[dict],
        *,
        runs_table_name: str,
        lock_token: str,
        worker_token: str,
        now: str,
    ) -> None:
        # One transaction fences both owners and inserts at most 98 children.
        self.dynamodb.transact_write(
            [
                {
                    "ConditionCheck": {
                        "TableName": runs_table_name,
                        "Key": {
                            "site_id": parent["site_id"],
                            "crawl_run_id": parent["crawl_run_id"],
                        },
                        "ConditionExpression": (
                            "discovery_lock_token = :token AND discovery_lock_expires_at > :now "
                            "AND #s = :working"
                        ),
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":token": lock_token,
                            ":now": now,
                            ":working": "CRAWLING_AND_PARSING",
                        },
                    }
                },
                {
                    "ConditionCheck": {
                        "TableName": self.dynamodb.table_name,
                        "Key": self.key(parent),
                        "ConditionExpression": (
                            "#s = :working AND worker_token = :token AND lease_expires_at > :now"
                        ),
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            ":working": "CRAWLING_AND_PARSING",
                            ":token": worker_token,
                            ":now": now,
                        },
                    }
                },
                *[
                    {
                        "Put": {
                            "TableName": self.dynamodb.table_name,
                            "Item": child,
                            "ConditionExpression": "attribute_not_exists(crawl_run_id)",
                        }
                    }
                    for child in children
                ],
            ]
        )
