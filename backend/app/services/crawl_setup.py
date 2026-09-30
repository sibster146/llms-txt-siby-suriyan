from hashlib import sha256
from typing import Any

from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.sites import SitesTable


class CrawlSetupService:
    """Prepare the site, run, and root page before publishing a crawl message."""

    def __init__(
        self, *, sites: SitesTable, crawl_runs: CrawlRunsTable, crawl_pages: CrawlPagesTable
    ) -> None:
        self.sites = sites
        self.crawl_runs = crawl_runs
        self.crawl_pages = crawl_pages

    def prepare(
        self,
        *,
        site_id: str,
        root_url: str,
        crawl_run_id: str,
        timestamp: str,
        resume_existing: bool = False,
    ) -> dict[str, Any] | None:
        canonical_url_hash = sha256(root_url.encode()).hexdigest()
        existing_run = (
            self.crawl_runs.get(site_id=site_id, crawl_run_id=crawl_run_id)
            if resume_existing
            else None
        )
        if existing_run is not None and existing_run.get("status") != "PENDING":
            return None

        self.sites.upsert_for_crawl(
            site_id=site_id, root_url=root_url, crawl_run_id=crawl_run_id, timestamp=timestamp
        )
        if existing_run is None:
            self.crawl_runs.create(site_id=site_id, crawl_run_id=crawl_run_id, created_at=timestamp)

        existing_page = (
            self.crawl_pages.get(crawl_run_id=crawl_run_id, canonical_url_hash=canonical_url_hash)
            if resume_existing
            else None
        )
        if existing_page is None:
            self.crawl_pages.create(
                crawl_run_id=crawl_run_id,
                canonical_url_hash=canonical_url_hash,
                site_id=site_id,
                url=root_url,
                depth=0,
                created_at=timestamp,
            )

        return {
            "action": "crawl_url",
            "payload": {
                "site_id": site_id,
                "crawl_run_id": crawl_run_id,
                "root_url": root_url,
                "url": root_url,
                "canonical_url_hash": canonical_url_hash,
                "depth": 0,
            },
        }
