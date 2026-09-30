"""EventBridge Scheduler entry point for nightly website refreshes."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3

BACKEND_PATH = Path(__file__).resolve().parent / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.clients.dynamodb import DynamoDBClient
from app.clients.sqs import SQSClient
from app.services.nightly_refresh import NightlyRefreshService
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.sites import SitesTable


@lru_cache
def _refresh_service() -> NightlyRefreshService:
    region = _required_env("AWS_REGION")
    session = boto3.Session(region_name=region)
    dynamodb = session.resource("dynamodb", region_name=region)

    def table(name: str) -> DynamoDBClient:
        return DynamoDBClient(table=dynamodb.Table(_required_env(name)))

    return NightlyRefreshService(
        sites=SitesTable(table("SITES_TABLE")),
        crawl_runs=CrawlRunsTable(table("CRAWL_RUNS_TABLE")),
        crawl_pages=CrawlPagesTable(table("CRAWL_PAGES_TABLE")),
        crawl_queue=SQSClient(
            session.client("sqs", region_name=region),
            _required_env("CRAWL_QUEUE_URL"),
        ),
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    """Queue one crawl run per site for this scheduled occurrence."""
    if event.get("action") != "nightly_refresh":
        raise ValueError("Event action must be 'nightly_refresh'")
    scheduled_time = event.get("scheduled_time")
    if not isinstance(scheduled_time, str):
        raise TypeError("Event scheduled_time must be a string")

    result = asdict(_refresh_service().refresh_all(scheduled_time=scheduled_time))
    print(json.dumps({"message": "Nightly refresh queued", **result}))
    return result


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
