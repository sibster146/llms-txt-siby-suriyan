from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class CreateLlmsTxtRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl


class CreateLlmsTxtResponse(BaseModel):
    site_id: str
    crawl_run_id: str
    url: HttpUrl
    status: Literal["PENDING"]


class CrawlStatusResponse(BaseModel):
    site_id: str
    crawl_run_id: str
    status: Literal[
        "PENDING",
        "CRAWLING_AND_PARSING",
        "GENERATING",
        "COMPLETED",
        "FAILED",
    ]
    pending_page_count: int
    discovered_page_count: int
    completed_page_count: int
    failed_page_count: int
    created_at: str
    updated_at: str | None = None


class SiteSummaryResponse(BaseModel):
    site_id: str
    root_url: HttpUrl
    last_crawl_run_id: str
    created_at: str
    updated_at: str
    modified_at: str | None = None
    latest_crawl: CrawlStatusResponse | None = None


class LlmsTxtVersionSummaryResponse(BaseModel):
    site_id: str
    version_id: str
    crawl_run_id: str
    generated_at: str
    content_hash: str
    status: str
    generation_method: str | None = None
    model_id: str | None = None


class LlmsTxtVersionResponse(LlmsTxtVersionSummaryResponse):
    content: str


class SiteDetailResponse(BaseModel):
    site_id: str
    root_url: HttpUrl
    created_at: str
    updated_at: str
    modified_at: str | None = None
    current_version: LlmsTxtVersionResponse | None = None
    versions: list[LlmsTxtVersionSummaryResponse]
