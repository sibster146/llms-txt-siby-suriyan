"""SQS Lambda entry point for parsing crawled HTML pages."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3

BACKEND_PATH = Path(__file__).resolve().parent / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.clients.dynamodb import DynamoDBClient
from app.clients.s3 import S3Client
from app.clients.sqs import SQSClient
from app.services.html_parser import HtmlParserService, ParseMessageError
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable


@lru_cache
def _html_parser_service() -> HtmlParserService:
    region = _required_env("AWS_REGION")
    session = boto3.Session(region_name=region)
    dynamodb = session.resource("dynamodb", region_name=region)
    sqs_client = session.client("sqs", region_name=region)

    return HtmlParserService(
        crawl_pages=CrawlPagesTable(
            DynamoDBClient(table=dynamodb.Table(_required_env("CRAWL_PAGES_TABLE")))
        ),
        crawl_runs=CrawlRunsTable(
            DynamoDBClient(table=dynamodb.Table(_required_env("CRAWL_RUNS_TABLE")))
        ),
        s3=S3Client(
            client=session.client("s3", region_name=region),
            bucket_name=_required_env("APPLICATION_S3_BUCKET"),
        ),
        crawl_queue=SQSClient(sqs_client, _required_env("CRAWL_QUEUE_URL")),
        llm_txt_queue=SQSClient(sqs_client, _required_env("LLM_TXT_QUEUE_URL")),
        parser_version=_required_env("PARSER_VERSION"),
        max_depth=int(_required_env("PARSER_MAX_DEPTH")),
        max_links_per_page=int(_required_env("PARSER_MAX_LINKS_PER_PAGE")),
        max_attempts=int(_required_env("PARSER_MAX_ATTEMPTS")),
    )


def _process_record(record: dict[str, Any]) -> None:
    try:
        message = json.loads(record.get("body", "{}"))
    except json.JSONDecodeError as error:
        raise ParseMessageError("Queued parser message must be valid JSON") from error
    if not isinstance(message, dict):
        raise ParseMessageError("Queued parser message must be an object")

    receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
    _html_parser_service().process_message(message, attempt=receive_count)


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process SQS records and return failures for individual retries."""
    if event.get("action") == "warmup":
        _html_parser_service()
        return {"warmed": True}

    batch_item_failures = []
    for record in event.get("Records", []):
        try:
            _process_record(record)
        except Exception as error:
            print(
                json.dumps(
                    {
                        "level": "error",
                        "message": "Failed processing parser message",
                        "message_id": record.get("messageId", ""),
                        "error": str(error),
                    }
                )
            )
            batch_item_failures.append({"itemIdentifier": record.get("messageId", "")})

    return {"batchItemFailures": batch_item_failures}


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
