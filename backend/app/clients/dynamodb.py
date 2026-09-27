from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


def to_dynamodb_value(value: Any) -> Any:
    """Convert Python domain values into values accepted by boto3 DynamoDB."""
    if isinstance(value, Enum):
        enum_value = value.value
        return enum_value.upper() if isinstance(enum_value, str) else to_dynamodb_value(enum_value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return to_dynamodb_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): to_dynamodb_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamodb_value(item) for item in value]
    return value


def dataclass_to_dynamodb_item(value: Any) -> dict[str, Any]:
    """Convert a dataclass instance into a DynamoDB-ready item."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError("value must be a dataclass instance")
    return to_dynamodb_value(asdict(value))


class DynamoDBClientError(Exception):
    """Raised when a DynamoDB operation fails."""

    def __init__(self, message: str, code: str = "DYNAMODB_CLIENT_ERROR") -> None:
        super().__init__(message)
        self.code = code


class DynamoDBClient:
    """Small application wrapper around one boto3 DynamoDB table resource."""

    def __init__(self, table: Any) -> None:
        self.table = table

    def put_item(self, item: dict[str, Any]) -> None:
        try:
            self.table.put_item(Item=to_dynamodb_value(item))
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to put item into DynamoDB: {error}",
                code="DYNAMODB_PUT_ITEM_FAILED",
            ) from error

    def batch_put_items(self, items: list[dict[str, Any]]) -> None:
        if not items:
            return

        try:
            with self.table.batch_writer() as batch:
                for item in items:
                    batch.put_item(Item=to_dynamodb_value(item))
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to batch put items into DynamoDB: {error}",
                code="DYNAMODB_BATCH_PUT_ITEMS_FAILED",
            ) from error

    def item_exists(self, key: dict[str, Any], consistent_read: bool = False) -> bool:
        try:
            response = self.table.get_item(Key=key, ConsistentRead=consistent_read)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to check item existence in DynamoDB: {error}",
                code="DYNAMODB_ITEM_EXISTS_FAILED",
            ) from error
        return "Item" in response

    def get_item(
        self,
        key: dict[str, Any],
        projection_expression: str | None = None,
        consistent_read: bool = False,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {
            "Key": key,
            "ConsistentRead": consistent_read,
        }
        if projection_expression:
            kwargs["ProjectionExpression"] = projection_expression

        try:
            response = self.table.get_item(**kwargs)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to get item from DynamoDB: {error}",
                code="DYNAMODB_GET_ITEM_FAILED",
            ) from error
        return response.get("Item")

    def query(self, key_condition: Any, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            response = self.table.query(KeyConditionExpression=key_condition, **kwargs)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to query DynamoDB: {error}",
                code="DYNAMODB_QUERY_FAILED",
            ) from error
        return response.get("Items", [])

    def scan(self, filter_expression: Any = None, **kwargs: Any) -> list[dict[str, Any]]:
        if filter_expression is not None:
            kwargs["FilterExpression"] = filter_expression

        try:
            response = self.table.scan(**kwargs)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to scan DynamoDB: {error}",
                code="DYNAMODB_SCAN_FAILED",
            ) from error
        return response.get("Items", [])

    def update_item(
        self,
        *,
        key: dict[str, Any],
        update_expression: str,
        expression_attribute_names: dict[str, str] | None = None,
        expression_attribute_values: dict[str, Any] | None = None,
        condition_expression: Any = None,
        return_values: str | None = None,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {
            "Key": key,
            "UpdateExpression": update_expression,
        }
        if expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = expression_attribute_names
        if expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = to_dynamodb_value(
                expression_attribute_values
            )
        if condition_expression is not None:
            kwargs["ConditionExpression"] = condition_expression
        if return_values:
            kwargs["ReturnValues"] = return_values

        try:
            response = self.table.update_item(**kwargs)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to update item in DynamoDB: {error}",
                code="DYNAMODB_UPDATE_ITEM_FAILED",
            ) from error
        return response.get("Attributes")

    def delete_item(self, key: dict[str, Any]) -> None:
        try:
            self.table.delete_item(Key=key)
        except Exception as error:
            raise DynamoDBClientError(
                message=f"Failed to delete item from DynamoDB: {error}",
                code="DYNAMODB_DELETE_ITEM_FAILED",
            ) from error
