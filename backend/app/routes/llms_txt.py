from contextlib import suppress
from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import HttpUrl

from app.clients.dynamodb import DynamoDBClientError
from app.clients.sqs import SQSClient, SQSClientError
from app.configs.dependencies import (
    get_crawl_pages_table,
    get_crawl_queue_client,
    get_crawl_runs_table,
    get_current_user_id,
    get_sites_table,
    get_user_sites_table,
)
from app.schemas.llms_txt import CreateLlmsTxtRequest, CreateLlmsTxtResponse
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable

router = APIRouter(prefix="/llms-txt", tags=["llms.txt"])


def _canonicalize_url(url: HttpUrl) -> str:
    parsed = urlsplit(str(url))
    hostname = parsed.hostname or ""
    port = parsed.port
    default_port = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc.lower(), path, parsed.query, ""))


@router.post("", response_model=CreateLlmsTxtResponse, status_code=status.HTTP_201_CREATED)
def create_llms_txt(
    payload: CreateLlmsTxtRequest,
    user_id: Annotated[str, Depends(get_current_user_id)],
    sites: Annotated[SitesTable, Depends(get_sites_table)],
    user_sites: Annotated[UserSitesTable, Depends(get_user_sites_table)],
    crawl_runs: Annotated[CrawlRunsTable, Depends(get_crawl_runs_table)],
    crawl_pages: Annotated[CrawlPagesTable, Depends(get_crawl_pages_table)],
    crawl_queue: Annotated[SQSClient, Depends(get_crawl_queue_client)],
) -> CreateLlmsTxtResponse:
    canonical_url = _canonicalize_url(payload.url)
    canonical_url_hash = sha256(canonical_url.encode()).hexdigest()
    site_id = f"site_{canonical_url_hash}"
    crawl_run_id = f"crawl_{uuid4()}"
    created_at = datetime.now(UTC).isoformat()

    try:
        sites.upsert_for_crawl(
            site_id=site_id,
            root_url=canonical_url,
            crawl_run_id=crawl_run_id,
            timestamp=created_at,
        )
        user_sites.add(
            user_id=user_id,
            site_id=site_id,
            created_at=created_at,
        )
        crawl_runs.create(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
            created_at=created_at,
        )
        crawl_pages.create(
            crawl_run_id=crawl_run_id,
            canonical_url_hash=canonical_url_hash,
            site_id=site_id,
            url=canonical_url,
            depth=0,
            created_at=created_at,
        )
    except DynamoDBClientError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The crawl request could not be saved.",
        ) from error

    try:
        crawl_queue.send_json(
            {
                "action": "crawl_url",
                "payload": {
                    "site_id": site_id,
                    "crawl_run_id": crawl_run_id,
                    "url": canonical_url,
                    "canonical_url_hash": canonical_url_hash,
                    "depth": 0,
                },
            }
        )
    except SQSClientError as error:
        with suppress(DynamoDBClientError):
            crawl_runs.update_status(
                site_id=site_id,
                crawl_run_id=crawl_run_id,
                crawl_status="FAILED",
                updated_at=datetime.now(UTC).isoformat(),
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The crawl request was saved but could not be queued.",
        ) from error

    return CreateLlmsTxtResponse(
        site_id=site_id,
        crawl_run_id=crawl_run_id,
        url=canonical_url,
        status="PENDING",
    )
