"""SQS Lambda entry point for generating versioned llms.txt files."""

# ruff: noqa: E402

from __future__ import annotations

import json
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

BACKEND_PATH = Path(__file__).resolve().parent / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))

from app.clients.bedrock import BedrockClient
from app.clients.dynamodb import DynamoDBClient
from app.clients.s3 import S3Client
from app.clients.sqs import SQSClient
from app.services.llms_txt_generator import (
    GenerationLeaseUnavailableError,
    GenerationMessageError,
    LlmsTxtGeneratorService,
)
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable


@lru_cache
def _generator_service() -> LlmsTxtGeneratorService:
    region = _required_env("AWS_REGION")
    session = boto3.Session(region_name=region)
    dynamodb = session.resource("dynamodb", region_name=region)
    bedrock_config = Config(
        connect_timeout=10,
        read_timeout=int(_required_env("BEDROCK_READ_TIMEOUT_SECONDS")),
        retries={"max_attempts": 3, "mode": "standard"},
    )

    def table(name: str) -> DynamoDBClient:
        return DynamoDBClient(table=dynamodb.Table(_required_env(name)))

    return LlmsTxtGeneratorService(
        sites=SitesTable(table("SITES_TABLE")),
        crawl_pages=CrawlPagesTable(table("CRAWL_PAGES_TABLE")),
        crawl_runs=CrawlRunsTable(table("CRAWL_RUNS_TABLE")),
        versions=LlmsTxtVersionsTable(table("LLM_TXT_VERSIONS_TABLE")),
        s3=S3Client(
            client=session.client("s3", region_name=region),
            bucket_name=_required_env("APPLICATION_S3_BUCKET"),
        ),
        bedrock=BedrockClient(
            client=session.client(
                "bedrock-runtime",
                region_name=region,
                config=bedrock_config,
            ),
            model_id=_required_env("BEDROCK_MODEL_ID"),
        ),
        max_input_pages=int(_required_env("GENERATOR_MAX_INPUT_PAGES")),
        max_output_links=int(_required_env("GENERATOR_MAX_OUTPUT_LINKS")),
        max_excerpt_chars=int(_required_env("GENERATOR_MAX_EXCERPT_CHARS")),
        max_model_tokens=int(_required_env("GENERATOR_MAX_MODEL_TOKENS")),
    )


def _decode_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        message = json.loads(record.get("body", "{}"))
    except json.JSONDecodeError as error:
        raise GenerationMessageError("Queued generator message must be valid JSON") from error
    if not isinstance(message, dict):
        raise GenerationMessageError("Queued generator message must be an object")
    return message


def _process_record(record: dict[str, Any]) -> None:
    message = _decode_record(record)
    _generator_service().process_message(message)


@lru_cache
def _retry_queues() -> tuple[SQSClient, SQSClient]:
    region = _required_env("AWS_REGION")
    client = boto3.Session(region_name=region).client("sqs", region_name=region)
    return (
        SQSClient(client, _required_env("LLM_TXT_QUEUE_URL")),
        SQSClient(client, _required_env("LLM_TXT_DLQ_URL")),
    )


def _schedule_failure(record: dict[str, Any], error: Exception) -> None:
    retry_queue, dead_letter_queue = _retry_queues()
    max_attempts = int(_required_env("GENERATOR_MAX_ATTEMPTS"))
    retry_delay = int(_required_env("GENERATOR_RETRY_DELAY_SECONDS"))

    try:
        message = _decode_record(record)
    except GenerationMessageError:
        dead_letter_queue.send_json(
            {
                "original_body": record.get("body", ""),
                "failure_reason": str(error),
            }
        )
        return

    attempt = int(message.get("retry_attempt", 1))
    if attempt < max_attempts:
        retry_queue.send_json(
            {**message, "retry_attempt": attempt + 1},
            delay_seconds=retry_delay,
        )
        return

    dead_letter_queue.send_json(
        {
            **message,
            "retry_attempt": attempt,
            "failure_reason": str(error),
        }
    )


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process SQS records and return failures for individual retries."""
    if event.get("action") == "warmup":
        _generator_service()
        return {"warmed": True}

    batch_item_failures = []
    for record in event.get("Records", []):
        try:
            _process_record(record)
        except GenerationLeaseUnavailableError as error:
            print(
                json.dumps(
                    {
                        "level": "info",
                        "message": "Generator message is already leased",
                        "message_id": record.get("messageId", ""),
                        "error": str(error),
                    }
                )
            )
            batch_item_failures.append({"itemIdentifier": record.get("messageId", "")})
        except Exception as error:
            print(
                json.dumps(
                    {
                        "level": "error",
                        "message": "Failed processing llms.txt generator message",
                        "message_id": record.get("messageId", ""),
                        "error": str(error),
                    }
                )
            )
            try:
                _schedule_failure(record, error)
            except Exception as scheduling_error:
                print(
                    json.dumps(
                        {
                            "level": "error",
                            "message": "Failed scheduling llms.txt generator retry",
                            "message_id": record.get("messageId", ""),
                            "error": str(scheduling_error),
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
