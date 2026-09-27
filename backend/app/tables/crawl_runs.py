from typing import Any

from boto3.dynamodb.conditions import Attr

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError


class CrawlRunsTable:
    """Persistence operations for crawl-run records."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    def create(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        created_at: str,
        force: bool = False,
        initial_page_count: int = 1,
    ) -> None:
        self.dynamodb.put_item(
            {
                "site_id": site_id,
                "crawl_run_id": crawl_run_id,
                "status": "PENDING",
                "pending_page_count": initial_page_count,
                "discovered_page_count": initial_page_count,
                "completed_page_count": 0,
                "failed_page_count": 0,
                "force": force,
                "created_at": created_at,
            }
        )

    def get(self, *, site_id: str, crawl_run_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(
            key={"site_id": site_id, "crawl_run_id": crawl_run_id}
        )

    def update_status(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        crawl_status: str,
        updated_at: str,
    ) -> None:
        self.dynamodb.update_item(
            key={"site_id": site_id, "crawl_run_id": crawl_run_id},
            update_expression="SET #status = :status, updated_at = :updated_at",
            expression_attribute_names={"#status": "status"},
            expression_attribute_values={
                ":status": crawl_status,
                ":updated_at": updated_at,
            },
        )

    def mark_crawled(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        updated_at: str,
    ) -> None:
        try:
            self.dynamodb.update_item(
                key={"site_id": site_id, "crawl_run_id": crawl_run_id},
                update_expression="SET #status = :status, updated_at = :updated_at",
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": "CRAWLED",
                    ":updated_at": updated_at,
                },
                condition_expression=(
                    Attr("status").not_exists()
                    | (
                        Attr("status").ne("GENERATION_QUEUED")
                        & Attr("status").ne("COMPLETED")
                    )
                ),
            )
        except DynamoDBConditionNotMetError:
            return

    def claim_generation(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        updated_at: str,
    ) -> bool:
        try:
            self.dynamodb.update_item(
                key={"site_id": site_id, "crawl_run_id": crawl_run_id},
                update_expression="SET #status = :status, updated_at = :updated_at",
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": "GENERATION_QUEUED",
                    ":updated_at": updated_at,
                },
                condition_expression=(
                    Attr("status").not_exists()
                    | (
                        Attr("status").ne("GENERATION_QUEUED")
                        & Attr("status").ne("COMPLETED")
                    )
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def release_generation_claim(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        updated_at: str,
    ) -> None:
        try:
            self.dynamodb.update_item(
                key={"site_id": site_id, "crawl_run_id": crawl_run_id},
                update_expression="SET #status = :status, updated_at = :updated_at",
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": "CRAWLED",
                    ":updated_at": updated_at,
                },
                condition_expression=Attr("status").eq("GENERATION_QUEUED"),
            )
        except DynamoDBConditionNotMetError:
            return

    def record_parsed_page(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        discovered_page_count: int,
        updated_at: str,
    ) -> dict[str, Any]:
        pending_delta = discovered_page_count - 1
        attributes = self.dynamodb.update_item(
            key={"site_id": site_id, "crawl_run_id": crawl_run_id},
            update_expression=(
                "SET updated_at = :updated_at "
                "ADD pending_page_count :pending_delta, "
                "discovered_page_count :discovered, completed_page_count :completed "
            ),
            expression_attribute_values={
                ":pending_delta": pending_delta,
                ":discovered": discovered_page_count,
                ":completed": 1,
                ":updated_at": updated_at,
            },
            return_values="ALL_NEW",
        )
        return attributes or {}
