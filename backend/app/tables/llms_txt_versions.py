from typing import Any

from boto3.dynamodb.conditions import Key

from app.clients.dynamodb import DynamoDBClient


class LlmsTxtVersionsTable:
    """Persistence operations for generated llms.txt versions."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        self.dynamodb = dynamodb

    def create(
        self,
        *,
        site_id: str,
        version_id: str,
        crawl_run_id: str,
        s3_key: str,
        content_hash: str,
        generated_at: str,
        version_status: str = "CURRENT",
    ) -> None:
        self.dynamodb.put_item(
            {
                "site_id": site_id,
                "version_id": version_id,
                "crawl_run_id": crawl_run_id,
                "llms_txt_s3_key": s3_key,
                "content_hash": content_hash,
                "status": version_status,
                "generated_at": generated_at,
            }
        )

    def get(self, *, site_id: str, version_id: str) -> dict[str, Any] | None:
        return self.dynamodb.get_item(key={"site_id": site_id, "version_id": version_id})

    def list_for_site(self, site_id: str) -> list[dict[str, Any]]:
        return self.dynamodb.query(
            key_condition=Key("site_id").eq(site_id),
            ScanIndexForward=False,
        )
