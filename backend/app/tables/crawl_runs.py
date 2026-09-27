from typing import Any

from app.clients.dynamodb import DynamoDBClient


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
