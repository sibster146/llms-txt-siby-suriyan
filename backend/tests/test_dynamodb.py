from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

import pytest

from app.clients.dynamodb import (
    DynamoDBClient,
    DynamoDBClientError,
    dataclass_to_dynamodb_item,
)
from app.configs.config import Settings


class Status(Enum):
    queued = "queued"


@dataclass
class CrawlRun:
    crawl_run_id: str
    status: Status
    score: float
    started_at: datetime


class FakeTable:
    def __init__(self) -> None:
        self.item: dict[str, Any] | None = None

    def put_item(self, *, Item: dict[str, Any]) -> None:
        self.item = Item


def test_dataclass_to_dynamodb_item_converts_domain_values() -> None:
    item = dataclass_to_dynamodb_item(
        CrawlRun(
            crawl_run_id="run-1",
            status=Status.queued,
            score=1.25,
            started_at=datetime(2026, 9, 27, tzinfo=UTC),
        )
    )

    assert item == {
        "crawl_run_id": "run-1",
        "status": "QUEUED",
        "score": Decimal("1.25"),
        "started_at": "2026-09-27T00:00:00+00:00",
    }


def test_put_item_converts_values_before_writing() -> None:
    table = FakeTable()

    DynamoDBClient(table).put_item({"score": 1.25})

    assert table.item == {"score": Decimal("1.25")}


def test_put_item_wraps_client_errors() -> None:
    class FailingTable:
        def put_item(self, **_: Any) -> None:
            raise RuntimeError("unavailable")

    with pytest.raises(DynamoDBClientError) as error:
        DynamoDBClient(FailingTable()).put_item({"site_id": "site-1"})

    assert error.value.code == "DYNAMODB_PUT_ITEM_FAILED"


@pytest.mark.parametrize("environment", ["dev", "prod"])
def test_settings_build_environment_specific_table_names(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("PROJECT_NAME", "llms_txt")
    monkeypatch.setenv("APPLICATION_S3_BUCKET", "dev-llms-txt-s3-test")
    monkeypatch.setenv(
        "CRAWL_QUEUE_URL",
        "https://sqs.us-east-1.amazonaws.com/123456789012/dev_llms_txt_crawl_sqs",
    )
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "test-pool")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "test-client")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")
    settings = Settings()

    assert settings.sites_dynamodb_table == f"{environment}_llms_txt_sites"
    assert settings.user_sites_dynamodb_table == f"{environment}_llms_txt_user_sites"
    assert settings.crawl_runs_dynamodb_table == f"{environment}_llms_txt_crawl_runs"
    assert settings.crawl_pages_dynamodb_table == f"{environment}_llms_txt_crawl_pages"
    assert (
        settings.llms_txt_versions_dynamodb_table
        == f"{environment}_llms_txt_llms_txt_versions"
    )
