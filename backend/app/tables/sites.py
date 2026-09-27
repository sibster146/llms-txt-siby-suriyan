from typing import Any

from boto3.dynamodb.conditions import Attr

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError


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
                "last_crawl_run_id = if_not_exists(last_crawl_run_id, :crawl_run_id), "
                "updated_at = :updated_at, "
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

    def mark_content_changed(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        modified_at: str,
    ) -> None:
        try:
            self.dynamodb.update_item(
                key={"site_id": site_id},
                update_expression=(
                    "SET last_crawl_run_id = :crawl_run_id, modified_at = :modified_at"
                ),
                expression_attribute_values={
                    ":crawl_run_id": crawl_run_id,
                    ":modified_at": modified_at,
                },
                condition_expression=(
                    Attr("modified_at").not_exists()
                    | Attr("modified_at").lt(modified_at)
                ),
            )
        except DynamoDBConditionNotMetError:
            return

    def get(self, site_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(key={"site_id": site_id})
