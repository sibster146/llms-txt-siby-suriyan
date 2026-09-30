"""Expose authenticated site lists, crawl requests/status, and generated versions.

User identity comes from the Cognito JWT dependency. Reads of site-specific
resources require a user-site mapping, returning 404 when access is absent.
"""

from datetime import UTC, datetime
from hashlib import sha256
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import HttpUrl

from app.clients.dynamodb import DynamoDBClientError
from app.clients.s3 import S3Client, S3ClientError
from app.clients.sqs import SQSClient, SQSClientError
from app.configs.dependencies import (
    get_crawl_pages_table,
    get_crawl_queue_client,
    get_crawl_runs_table,
    get_current_user_id,
    get_llms_txt_versions_table,
    get_s3_client,
    get_sites_table,
    get_user_sites_table,
)
from app.schemas.llms_txt import (
    CrawlStatusResponse,
    CreateLlmsTxtRequest,
    CreateLlmsTxtResponse,
    LlmsTxtVersionResponse,
    SiteDetailResponse,
    SiteSummaryResponse,
)
from app.services.crawl_setup import CrawlSetupService
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable

router = APIRouter(prefix="/llms-txt", tags=["llms.txt"])


def _crawl_not_found() -> HTTPException:
    """Build the shared HTTP 404 for missing crawls or missing site membership."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Crawl not found.",
    )


def _site_not_found() -> HTTPException:
    """Build the shared HTTP 404 for missing sites or missing site membership."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Website not found.",
    )


def _version_not_found() -> HTTPException:
    """Build the shared HTTP 404 for missing versions or missing site membership."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="llms.txt version not found.",
    )


def _canonicalize_url(url: HttpUrl) -> str:
    """Normalize a validated input URL before deriving the site's hash and root URL.

    Lowercase scheme/host, omit default ports and fragments, and supply '/' for
    an empty path. Preserve the path and query; no request or DNS check is made.
    """
    parsed = urlsplit(str(url))
    hostname = parsed.hostname or ""
    port = parsed.port
    default_port = (parsed.scheme == "http" and port == 80) or (
        parsed.scheme == "https" and port == 443
    )
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc.lower(), path, parsed.query, ""))


@router.get("/sites", response_model=list[SiteSummaryResponse])
def list_user_sites(
    user_id: Annotated[str, Depends(get_current_user_id)],
    sites: Annotated[SitesTable, Depends(get_sites_table)],
    user_sites: Annotated[UserSitesTable, Depends(get_user_sites_table)],
    crawl_runs: Annotated[CrawlRunsTable, Depends(get_crawl_runs_table)],
    crawl_pages: Annotated[CrawlPagesTable, Depends(get_crawl_pages_table)],
) -> list[SiteSummaryResponse]:
    """List the authenticated user's sites, newest content modification first.

    Resolve user-site mappings, skip missing sites, and attach the latest crawl
    with counts derived from its page records. Fall back to last_crawl_run_id
    for older site records. Map caught DynamoDB and missing-field errors to 502.
    """
    try:
        mappings = user_sites.list_for_user(user_id)
        site_records: list[dict[str, object]] = []
        for mapping in mappings:
            site = sites.get(str(mapping["site_id"]))
            if site is None:
                continue
            # latest: whenever a crawl happens; last: a change happened on the site.
            crawl_run_id = str(site.get("latest_crawl_run_id") or site["last_crawl_run_id"])
            crawl_run = crawl_runs.get(
                site_id=str(site["site_id"]),
                crawl_run_id=crawl_run_id,
            )
            if crawl_run is not None:
                crawl_run = {**crawl_run, **crawl_pages.counts_for_run(crawl_run_id)}
            site_records.append({**site, "latest_crawl": crawl_run})
    except (DynamoDBClientError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The websites could not be loaded.",
        ) from error

    site_records.sort(
        key=lambda site: str(site.get("modified_at", "")),
        reverse=True,
    )
    return [SiteSummaryResponse.model_validate(site) for site in site_records]


@router.get("/sites/{site_id}", response_model=SiteDetailResponse)
def get_site_detail(
    site_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    sites: Annotated[SitesTable, Depends(get_sites_table)],
    user_sites: Annotated[UserSitesTable, Depends(get_user_sites_table)],
    crawl_runs: Annotated[CrawlRunsTable, Depends(get_crawl_runs_table)],
    crawl_pages: Annotated[CrawlPagesTable, Depends(get_crawl_pages_table)],
    versions: Annotated[LlmsTxtVersionsTable, Depends(get_llms_txt_versions_table)],
    s3: Annotated[S3Client, Depends(get_s3_client)],
) -> SiteDetailResponse:
    """Return an accessible site's current text, version list, and latest crawl.

    Require user-site membership before reading details. Derive current crawl
    counts from pages and load only the current version's body from S3; the
    version list contains metadata. Missing membership/site returns HTTP 404;
    caught DynamoDB, S3, or missing-field errors return 502.
    """
    try:
        mapping = user_sites.get(user_id=user_id, site_id=site_id)
        if mapping is None:
            raise _site_not_found()
        site = sites.get(site_id)
        if site is None:
            raise _site_not_found()
        crawl_run_id = str(site.get("latest_crawl_run_id") or site["last_crawl_run_id"])
        latest_crawl = crawl_runs.get(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
        )
        if latest_crawl is not None:
            latest_crawl = {**latest_crawl, **crawl_pages.counts_for_run(crawl_run_id)}
        version_records = versions.list_for_site(site_id)
        current_version_id = site.get("current_llms_txt_version_id")
        current_record = next(
            (
                version
                for version in version_records
                if version.get("version_id") == current_version_id
            ),
            None,
        )
        current_version = None
        if current_record is not None:
            current_version = {
                **current_record,
                "content": s3.get_text(str(current_record["llms_txt_s3_key"])),
            }
    except HTTPException:
        raise
    except (DynamoDBClientError, S3ClientError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The website details could not be loaded.",
        ) from error

    return SiteDetailResponse.model_validate(
        {
            **site,
            "latest_crawl": latest_crawl,
            "current_version": current_version,
            "versions": version_records,
        }
    )


@router.get(
    "/sites/{site_id}/versions/{version_id}",
    response_model=LlmsTxtVersionResponse,
)
def get_llms_txt_version(
    site_id: str,
    version_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    user_sites: Annotated[UserSitesTable, Depends(get_user_sites_table)],
    versions: Annotated[LlmsTxtVersionsTable, Depends(get_llms_txt_versions_table)],
    s3: Annotated[S3Client, Depends(get_s3_client)],
) -> LlmsTxtVersionResponse:
    """Return one version's metadata and S3 text after checking site membership.

    Used to open current or historical files. Missing membership or version
    returns HTTP 404; caught storage or missing-field failures return 502.
    """
    try:
        if user_sites.get(user_id=user_id, site_id=site_id) is None:
            raise _version_not_found()
        version = versions.get(site_id=site_id, version_id=version_id)
        if version is None:
            raise _version_not_found()
        content = s3.get_text(str(version["llms_txt_s3_key"]))
    except HTTPException:
        raise
    except (DynamoDBClientError, S3ClientError, KeyError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The llms.txt version could not be loaded.",
        ) from error

    return LlmsTxtVersionResponse.model_validate({**version, "content": content})


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
    """Start an asynchronous crawl for the authenticated user and return HTTP 201.

    Normalize the URL into a stable site ID and allocate a fresh crawl UUID.
    Shared setup atomically writes the site/run/root page, then a separate write
    associates the user with the site. Publish the root SQS message only after
    these writes succeed, returning IDs and PENDING rather than waiting for output.
    Storage and queue failures return distinct 502 messages; earlier successful
    writes are not rolled back. Repeated calls create separate crawl runs.
    """
    canonical_url = _canonicalize_url(payload.url)
    canonical_url_hash = sha256(canonical_url.encode()).hexdigest()
    site_id = f"site_{canonical_url_hash}"
    crawl_run_id = f"crawl_{uuid4()}"
    created_at = datetime.now(UTC).isoformat()

    try:
        message = CrawlSetupService(
            sites=sites, crawl_runs=crawl_runs, crawl_pages=crawl_pages
        ).prepare(
            site_id=site_id,
            root_url=canonical_url,
            crawl_run_id=crawl_run_id,
            timestamp=created_at,
        )
        user_sites.add(
            user_id=user_id,
            site_id=site_id,
            crawl_run_id=crawl_run_id,
            timestamp=created_at,
        )
    except DynamoDBClientError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The crawl request could not be saved.",
        ) from error

    try:
        assert message is not None
        crawl_queue.send_json(message)
    except SQSClientError as error:
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


@router.get(
    "/{site_id}/crawls/{crawl_run_id}",
    response_model=CrawlStatusResponse,
)
def get_crawl_status(
    site_id: str,
    crawl_run_id: str,
    user_id: Annotated[str, Depends(get_current_user_id)],
    user_sites: Annotated[UserSitesTable, Depends(get_user_sites_table)],
    crawl_runs: Annotated[CrawlRunsTable, Depends(get_crawl_runs_table)],
    crawl_pages: Annotated[CrawlPagesTable, Depends(get_crawl_pages_table)],
) -> CrawlStatusResponse:
    """Return a crawl snapshot and page-derived counts for frontend polling.

    Require site membership and an existing run, returning HTTP 404 otherwise.
    Map DynamoDB errors during membership/run lookup to 502. Counts are fetched
    afterward, outside that error handler; this is a single read response, not
    a server-held long-poll request.
    """
    try:
        if user_sites.get(user_id=user_id, site_id=site_id) is None:
            raise _crawl_not_found()
        crawl_run = crawl_runs.get(site_id=site_id, crawl_run_id=crawl_run_id)
    except HTTPException:
        raise
    except DynamoDBClientError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The crawl status could not be loaded.",
        ) from error

    if crawl_run is None:
        raise _crawl_not_found()

    return CrawlStatusResponse.model_validate(
        {**crawl_run, **crawl_pages.counts_for_run(crawl_run_id)}
    )
