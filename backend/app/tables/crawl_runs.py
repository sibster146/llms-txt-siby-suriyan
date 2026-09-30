import contextlib
from typing import Any

from boto3.dynamodb.conditions import Attr

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError


class CrawlRunsTable:
    """Run lifecycle, discovery lock, and durable generation dispatch."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    @staticmethod
    def new_item(*, site_id: str, crawl_run_id: str, created_at: str, root_url: str) -> dict:
        return dict(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
            created_at=created_at,
            updated_at=created_at,
            root_url=root_url,
            status="PENDING",
        )

    def get(self, *, site_id: str, crawl_run_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id), consistent_read=True
        )

    def list_active(self) -> list[dict[str, Any]]:
        return self.dynamodb.scan(
            Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING", "GENERATING"]),
            ConsistentRead=True,
        )

    def acquire_discovery_lock(
        self, *, site_id: str, crawl_run_id: str, token: str, now: str, expires_at: str
    ) -> bool:
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET discovery_lock_token = :token, discovery_lock_expires_at = :expiry"
                ),
                expression_attribute_values={":token": token, ":expiry": expires_at},
                condition_expression=(
                    Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                    & (
                        Attr("discovery_lock_expires_at").not_exists()
                        | Attr("discovery_lock_expires_at").lte(now)
                    )
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def release_discovery_lock(self, *, site_id: str, crawl_run_id: str, token: str) -> None:
        with contextlib.suppress(DynamoDBConditionNotMetError):
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression="REMOVE discovery_lock_token, discovery_lock_expires_at",
                condition_expression=Attr("discovery_lock_token").eq(token),
            )

    def claim_generation(
        self, *, site_id: str, crawl_run_id: str, token: str, updated_at: str
    ) -> bool:
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET #s = :generating, generation_dispatch_pending = :yes, updated_at = :now "
                    "REMOVE discovery_lock_token, discovery_lock_expires_at"
                ),
                expression_attribute_names={"#s": "status"},
                expression_attribute_values={
                    ":generating": "GENERATING",
                    ":yes": True,
                    ":now": updated_at,
                },
                condition_expression=(
                    Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                    & Attr("discovery_lock_token").eq(token)
                    & Attr("discovery_lock_expires_at").gt(updated_at)
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def mark_generation_sent(self, *, site_id: str, crawl_run_id: str) -> None:
        with contextlib.suppress(DynamoDBConditionNotMetError):
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression="SET generation_dispatch_pending = :no",
                expression_attribute_values={":no": False},
                condition_expression=Attr("status").eq("GENERATING"),
            )

    def fail_empty_run(
        self, *, site_id: str, crawl_run_id: str, token: str, updated_at: str
    ) -> None:
        self.dynamodb.update_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
            update_expression=(
                "SET #s = :failed, updated_at = :now, error_message = :error "
                "REMOVE discovery_lock_token, discovery_lock_expires_at"
            ),
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":failed": "FAILED",
                ":now": updated_at,
                ":error": "No pages could be crawled and parsed successfully",
            },
            condition_expression=(
                Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                & Attr("discovery_lock_token").eq(token)
                & Attr("discovery_lock_expires_at").gt(updated_at)
            ),
        )

    def mark_generation_completed(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        version_id: str,
        crawl_content_hash: str,
        generated_at: str,
    ) -> None:
        self.dynamodb.update_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
            update_expression=(
                "SET #s = :status, llms_txt_version_id = :version, "
                "crawl_content_hash = :hash, generated_at = :now, updated_at = :now "
                "REMOVE generation_dispatch_pending"
            ),
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":status": "COMPLETED",
                ":version": version_id,
                ":hash": crawl_content_hash,
                ":now": generated_at,
            },
            condition_expression=Attr("status").is_in(["GENERATING", "COMPLETED"]),
        )

    def mark_generation_failed(
        self, *, site_id: str, crawl_run_id: str, error_message: str, updated_at: str
    ) -> bool:
        """Finalize exhausted generation without changing missing or terminal runs."""
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET #s = :failed, error_message = :error, updated_at = :now "
                    "REMOVE generation_dispatch_pending"
                ),
                expression_attribute_names={"#s": "status"},
                expression_attribute_values={
                    ":failed": "FAILED",
                    ":error": error_message[:1000],
                    ":now": updated_at,
                },
                condition_expression=Attr("status").eq("GENERATING"),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True
