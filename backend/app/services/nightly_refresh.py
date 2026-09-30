from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from app.clients.sqs import SQSClient
from app.services.crawl_setup import CrawlSetupService
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.sites import SitesTable


class NightlyRefreshError(Exception):
    """Raised when one or more sites cannot be queued for nightly refresh."""


@dataclass(frozen=True)
class NightlyRefreshResult:
    discovered_sites: int
    queued_sites: int
    skipped_sites: int


class NightlyRefreshService:
    """Start one retry-safe crawl run for every registered site."""

    def __init__(
        self,
        *,
        sites: SitesTable,
        crawl_runs: CrawlRunsTable,
        crawl_pages: CrawlPagesTable,
        crawl_queue: SQSClient,
    ) -> None:
        self.sites = sites
        self.crawl_runs = crawl_runs
        self.crawl_pages = crawl_pages
        self.crawl_queue = crawl_queue

    def refresh_all(self, *, scheduled_time: str) -> NightlyRefreshResult:
        if not scheduled_time.strip():
            raise NightlyRefreshError("scheduled_time is required")
        try:
            parsed_time = datetime.fromisoformat(scheduled_time.strip())
            if parsed_time.tzinfo is None:
                raise ValueError("timezone is required")
        except ValueError as error:
            raise NightlyRefreshError(
                "scheduled_time must be an ISO timestamp with timezone"
            ) from error

        site_records = self.sites.list_all()
        queued_sites = 0
        skipped_sites = 0
        failures: list[str] = []

        for site in site_records:
            try:
                if self._queue_site(site, scheduled_time.strip()):
                    queued_sites += 1
                else:
                    skipped_sites += 1
            except Exception as error:
                failures.append(f"{site.get('site_id', 'unknown')}: {error}")

        if failures:
            raise NightlyRefreshError(
                f"Failed to queue {len(failures)} site(s): {'; '.join(failures)}"
            )

        return NightlyRefreshResult(
            discovered_sites=len(site_records),
            queued_sites=queued_sites,
            skipped_sites=skipped_sites,
        )

    def _queue_site(self, site: dict[str, Any], scheduled_time: str) -> bool:
        site_id = _required_site_value(site, "site_id")
        root_url = _required_site_value(site, "root_url")
        crawl_run_id = _scheduled_crawl_run_id(site_id, scheduled_time)
        message = CrawlSetupService(
            sites=self.sites, crawl_runs=self.crawl_runs, crawl_pages=self.crawl_pages
        ).prepare(
            site_id=site_id,
            root_url=root_url,
            crawl_run_id=crawl_run_id,
            timestamp=scheduled_time,
            resume_existing=True,
        )
        if message is None:
            return False
        self.crawl_queue.send_json(message)
        return True


def _scheduled_crawl_run_id(site_id: str, scheduled_time: str) -> str:
    digest = sha256(f"{scheduled_time}:{site_id}".encode()).hexdigest()
    return f"crawl_{digest}"


def _required_site_value(site: dict[str, Any], key: str) -> str:
    value = site.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NightlyRefreshError(f"Site record is missing {key}")
    return value.strip()
