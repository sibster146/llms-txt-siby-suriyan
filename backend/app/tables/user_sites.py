from typing import Any

from boto3.dynamodb.conditions import Key

from app.clients.dynamodb import DynamoDBClient


class UserSitesTable:
    """Persistence operations for user-to-site mappings."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        """Bind the environment's UserSites client during API dependency setup.

        Mappings use user_id as partition key and site_id as sort key.
        Construction performs no database operations.
        """
        self.dynamodb = dynamodb

    def add(
        self,
        *,
        user_id: str,
        site_id: str,
        crawl_run_id: str,
        timestamp: str,
    ) -> None:
        """Create or refresh a user's association with a requested site.

        POST /llms-txt calls this after crawl setup and before sending the root
        message. user_id comes from the validated Cognito token; crawl_run_id is
        the run requested by that user. Preserves the original created_at while
        updating last_crawl_run_id and updated_at to the supplied values.

        This write is separate from the site/run/root transaction. It neither
        creates a Cognito user nor starts a crawl or sends an SQS message.
        """
        self.dynamodb.update_item(
            key={"user_id": user_id, "site_id": site_id},
            update_expression=(
                "SET created_at = if_not_exists(created_at, :created_at), "
                "last_crawl_run_id = :crawl_run_id, updated_at = :updated_at"
            ),
            expression_attribute_values={
                ":created_at": timestamp,
                ":crawl_run_id": crawl_run_id,
                ":updated_at": timestamp,
            },
        )

    def get(self, *, user_id: str, site_id: str) -> dict[str, Any] | None:
        """Read one user-to-site mapping, returning None if absent.

        Site detail, version retrieval, and crawl-status routes use this to check
        whether the authenticated user is associated with the requested site.
        Uses default eventual consistency; the caller handles authorization errors.
        """
        return self.dynamodb.get_item(key={"user_id": user_id, "site_id": site_id})

    def list_for_user(self, user_id: str) -> list[dict[str, Any]]:
        """Return all mappings for a user through a paginated partition-key query.

        The homepage's site-list route uses their site IDs to fetch Sites records
        and current crawl progress. Returns mappings, not site details or generated
        file contents, using default eventual consistency.
        """
        return self.dynamodb.query(key_condition=Key("user_id").eq(user_id))
