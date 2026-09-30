from typing import Any

from boto3.dynamodb.conditions import Key

from app.clients.dynamodb import DynamoDBClient


class LlmsTxtVersionsTable:
    """Persistence operations for generated llms.txt versions."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        """Bind the environment's version table during API or generator setup.

        Records use site_id as partition key and version_id as sort key.
        Construction performs no database operations.
        """
        self.dynamodb = dynamodb

    def create(
        self,
        *,
        site_id: str,
        version_id: str,
        crawl_run_id: str,
        s3_key: str,
        content_hash: str,
        crawl_content_hash: str,
        generated_at: str,
        generation_method: str | None = None,
        model_id: str | None = None,
        version_status: str = "CURRENT",
    ) -> None:
        """Persist metadata for a generated file after its S3 write succeeds.

        The generator calls this before updating the site and run completion
        records. s3_key locates the file; content_hash identifies its text, while
        crawl_content_hash identifies the source crawl manifest used for reuse.
        generated_at records the version's generation time. Optional generation
        method and model ID are stored only when truthy.

        Writes at (site_id, version_id) without an existence condition, so an
        existing item at that key is replaced. version_status defaults to CURRENT,
        but this method does not demote older versions or update the site pointer.
        The Sites record determines which version is currently displayed.
        """
        item = {
            "site_id": site_id,
            "version_id": version_id,
            "crawl_run_id": crawl_run_id,
            "llms_txt_s3_key": s3_key,
            "content_hash": content_hash,
            "crawl_content_hash": crawl_content_hash,
            "status": version_status,
            "generated_at": generated_at,
        }
        if generation_method:
            item["generation_method"] = generation_method
        if model_id:
            item["model_id"] = model_id
        self.dynamodb.put_item(item)

    def get(self, *, site_id: str, version_id: str) -> dict[str, Any] | None:
        """Read version metadata by its complete key, or return None if absent.

        Used for API version downloads and generator retries/content reuse.
        Uses default eventual consistency. The caller reads llms_txt_s3_key from
        the returned record to retrieve the actual text separately from S3.
        """
        return self.dynamodb.get_item(key={"site_id": site_id, "version_id": version_id})

    def list_for_site(self, site_id: str) -> list[dict[str, Any]]:
        """Return all version records for a site in descending version_id order.

        The site-detail route uses this paginated query for current-version lookup
        and version history. Timestamp-prefixed IDs provide chronological ordering;
        the query sorts by version_id, not generated_at. Uses default eventual
        consistency and returns metadata only, without fetching S3 file contents.
        """
        return self.dynamodb.query(
            key_condition=Key("site_id").eq(site_id),
            ScanIndexForward=False,
        )
