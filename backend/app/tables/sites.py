from typing import Any

from app.clients.dynamodb import DynamoDBClient


class SitesTable:
    """Persistence operations for website records."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    def upsert_for_crawl(
        self,
        *,
        site_id: str,
        root_url: str,
        crawl_run_id: str,
        timestamp: str,
    ) -> None:
        self.dynamodb.update_item(
            key={"site_id": site_id},
            update_expression=(
                "SET root_url = :root_url, normalized_root_url = :normalized_root_url, "
                "last_crawl_run_id = :crawl_run_id, updated_at = :updated_at, "
                "created_at = if_not_exists(created_at, :created_at)"
            ),
            expression_attribute_values={
                ":root_url": root_url,
                ":normalized_root_url": root_url,
                ":crawl_run_id": crawl_run_id,
                ":updated_at": timestamp,
                ":created_at": timestamp,
            },
        )

    def get(self, site_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(key={"site_id": site_id})
