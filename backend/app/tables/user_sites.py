from typing import Any

from boto3.dynamodb.conditions import Key

from app.clients.dynamodb import DynamoDBClient


class UserSitesTable:
    """Persistence operations for user-to-site mappings."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    def add(self, *, user_id: str, site_id: str, created_at: str) -> None:
        self.dynamodb.update_item(
            key={"user_id": user_id, "site_id": site_id},
            update_expression="SET created_at = if_not_exists(created_at, :created_at)",
            expression_attribute_values={":created_at": created_at},
        )

    def get(self, *, user_id: str, site_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(key={"user_id": user_id, "site_id": site_id})

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        return self.dynamodb.query(key_condition=Key("user_id").eq(user_id))
