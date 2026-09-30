from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import boto3
import pytest
from moto import mock_aws

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError
from app.clients.sqs import SQSClientError
from app.services.crawl_and_parse import (
    CrawlAndParseService,
    FetchedPage,
    PageNotFoundError,
    ResponseTooLargeError,
    WorkDeferred,
    after,
    now,
)
from app.services.crawl_setup import CrawlSetupService
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.sites import SitesTable


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.writes = []

    def object_exists(self, key):
        return key in self.objects

    def get_bytes(self, key):
        return self.objects[key]

    def put_bytes(self, *, key, content, **kwargs):
        self.objects[key] = content
        self.writes.append(key)
        return key

    def put_text(self, *, key, content, **kwargs):
        return self.put_bytes(key=key, content=content.encode())


@pytest.fixture
def workflow():
    with mock_aws():
        db = boto3.resource("dynamodb", region_name="us-east-1")
        tables = {}
        for name, keys in [
            ("sites", ["site_id"]),
            ("runs", ["site_id", "crawl_run_id"]),
            ("pages", ["crawl_run_id", "canonical_url_hash"]),
        ]:
            kwargs = dict(
                TableName=name,
                BillingMode="PAY_PER_REQUEST",
                KeySchema=[
                    {"AttributeName": k, "KeyType": "HASH" if i == 0 else "RANGE"}
                    for i, k in enumerate(keys)
                ],
                AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in keys],
            )
            if name == "pages":
                kwargs["AttributeDefinitions"] += [
                    {"AttributeName": k, "AttributeType": "S"}
                    for k in ["site_url_key", "crawled_at"]
                ]
                kwargs["GlobalSecondaryIndexes"] = [
                    {
                        "IndexName": "site_url_crawled_at_index",
                        "KeySchema": [
                            {"AttributeName": "site_url_key", "KeyType": "HASH"},
                            {"AttributeName": "crawled_at", "KeyType": "RANGE"},
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                    }
                ]
            tables[name] = DynamoDBClient(db.create_table(**kwargs))
        pages = CrawlPagesTable(tables["pages"])
        runs = CrawlRunsTable(tables["runs"])
        sites = SitesTable(tables["sites"])
        setup = CrawlSetupService(sites=sites, crawl_runs=runs, crawl_pages=pages)
        message = setup.prepare(
            site_id="site", root_url="https://example.com/", crawl_run_id="run", timestamp=now()
        )
        fetch = Mock(
            return_value=FetchedPage(
                b"<html><title>Example</title><p>Hello world</p></html>",
                "text/html",
                "https://example.com/",
                200,
            )
        )
        queue, generation, s3 = Mock(), Mock(), MemoryS3()
        service = CrawlAndParseService(
            crawl_pages=pages,
            crawl_runs=runs,
            sites=sites,
            s3=s3,
            crawl_queue=queue,
            llm_txt_queue=generation,
            user_agent="test",
            request_timeout_seconds=1,
            max_response_bytes=1000,
            max_attempts=2,
            retry_delay_seconds=30,
            lease_seconds=150,
            parser_version="v2",
            max_depth=2,
            max_links_per_page=100,
            max_discovered_pages=1000,
            fetch_page=fetch,
            robots_checker=lambda *_: True,
            sitemap_discoverer=lambda *_: [],
        )
        yield SimpleNamespace(
            service=service,
            pages=pages,
            runs=runs,
            sites=sites,
            setup=setup,
            message=message,
            fetch=fetch,
            queue=queue,
            generation=generation,
            s3=s3,
            tables=tables,
        )


def root(w):
    return w.pages.list_for_run("run")[0]


def claim(w, token="worker"):
    p = root(w)
    assert w.pages.claim(
        p, runs_table_name="runs", token=token, now=now(), expires_at=after(150), max_attempts=2
    )
    return root(w)


def expire(w, page):
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    w.tables["pages"].update_item(
        key=w.pages.key(page),
        update_expression="SET lease_expires_at = :past, retry_after = :past",
        expression_attribute_values={":past": past},
    )


def test_single_page_finishes_and_dispatches_generation_once(workflow):
    w = workflow
    w.service.process_message(w.message)
    w.service.process_message(w.message)
    assert root(w)["status"] == "COMPLETED"
    assert root(w)["attempt_count"] == 1
    assert w.runs.get(site_id="site", crawl_run_id="run")["status"] == "GENERATING"
    w.fetch.assert_called_once()
    w.generation.send_json.assert_called_once()
    assert not any(
        k.endswith("_page_count") for k in w.runs.get(site_id="site", crawl_run_id="run")
    )
    assert w.pages.counts_for_run("run") == dict(
        discovered_page_count=1, pending_page_count=0, completed_page_count=1, failed_page_count=0
    )


def test_duplicate_active_delivery_does_not_claim_or_fetch(workflow):
    w = workflow
    claim(w)
    with pytest.raises(WorkDeferred):
        w.service.process_message(w.message)
    assert root(w)["attempt_count"] == 1
    w.fetch.assert_not_called()


def test_expired_worker_cannot_complete_or_register_children(workflow):
    w = workflow
    old = claim(w, "old")
    expire(w, old)
    assert w.pages.claim(
        root(w),
        runs_table_name="runs",
        token="new",
        now=now(),
        expires_at=after(150),
        max_attempts=2,
    )
    with pytest.raises(DynamoDBConditionNotMetError):
        w.pages.finish(old, token="old", now=now())
    assert w.runs.acquire_discovery_lock(
        site_id="site", crawl_run_id="run", token="lock", now=now(), expires_at=after(30)
    )
    child = w.pages.new_item(
        crawl_run_id="run",
        site_id="site",
        canonical_url_hash="child",
        url="https://example.com/a",
        root_url="https://example.com/",
        depth=1,
        created_at=now(),
    )
    with pytest.raises(DynamoDBConditionNotMetError):
        w.pages.register_children(
            old, [child], runs_table_name="runs", lock_token="lock", worker_token="old", now=now()
        )
    assert len(w.pages.list_for_run("run")) == 1


def test_discovery_lock_fences_old_owner_and_enforces_cap(workflow):
    w = workflow
    parent = claim(w)
    parent["children_root_url"] = parent["root_url"]
    assert w.runs.acquire_discovery_lock(
        site_id="site", crawl_run_id="run", token="other", now=now(), expires_at=after(30)
    )
    with pytest.raises(WorkDeferred):
        w.service._register_children(parent, "worker", ["https://example.com/a"])
    w.runs.release_discovery_lock(site_id="site", crawl_run_id="run", token="wrong")
    assert w.runs.get(site_id="site", crawl_run_id="run")["discovery_lock_token"] == "other"
    w.runs.release_discovery_lock(site_id="site", crawl_run_id="run", token="other")
    w.service.max_pages = 2
    w.service._register_children(
        parent, "worker", ["https://example.com/a", "https://example.com/b"]
    )
    w.service._register_children(
        parent, "worker", ["https://example.com/a", "https://example.com/c"]
    )
    assert len(w.pages.list_for_run("run")) == 2


def test_children_exist_before_parent_finishes_and_block_generation(workflow):
    w = workflow
    w.fetch.return_value = FetchedPage(
        b'<html><a href="/child">Child</a><a href="/child">Duplicate</a></html>',
        "text/html",
        "https://example.com/",
        200,
    )
    w.service.process_message(w.message)
    pages = w.pages.list_for_run("run")
    assert sorted(p["status"] for p in pages) == ["COMPLETED", "QUEUED"]
    w.generation.send_json.assert_not_called()
    child_message = w.queue.send_json.call_args.args[0]
    w.fetch.return_value = FetchedPage(
        b"<html>Child</html>", "text/html", "https://example.com/child", 200
    )
    w.service.process_message(child_message)
    w.generation.send_json.assert_called_once()


@pytest.mark.parametrize("error", [PageNotFoundError("404"), ResponseTooLargeError("large")])
def test_permanent_failures_do_not_retry(workflow, error):
    w = workflow
    w.fetch.side_effect = error
    w.service.process_message(w.message)
    assert root(w)["status"] == "FAILED"
    w.queue.send_json.assert_not_called()


def test_two_actual_attempts_with_30_second_delay(workflow):
    w = workflow
    w.fetch.side_effect = RuntimeError("network")
    start = datetime.now(UTC)
    w.service.process_message(w.message)
    page = root(w)
    assert page["status"] == "CRAWLING_AND_PARSING"
    assert (datetime.fromisoformat(page["retry_after"]) - start).total_seconds() >= 30
    assert w.queue.send_json.call_args.kwargs["delay_seconds"] == 30
    with pytest.raises(WorkDeferred):
        w.service.process_message(w.message)
    expire(w, page)
    w.service.process_message(w.message)
    assert root(w)["status"] == "FAILED"
    assert w.fetch.call_count == 2


def test_recovery_fails_expired_final_attempt_without_fetching(workflow):
    w = workflow
    p = claim(w)
    expire(w, p)
    w.pages.claim(
        root(w),
        runs_table_name="runs",
        token="second",
        now=now(),
        expires_at=after(150),
        max_attempts=2,
    )
    expire(w, root(w))
    w.service.recover()
    assert root(w)["status"] == "FAILED"
    w.fetch.assert_not_called()
    w.generation.send_json.assert_not_called()
    assert w.runs.get(site_id="site", crawl_run_id="run")["status"] == "FAILED"


def test_recovery_does_not_fail_active_final_attempt(workflow):
    w = workflow
    p = claim(w)
    expire(w, p)
    w.pages.claim(
        root(w),
        runs_table_name="runs",
        token="second",
        now=now(),
        expires_at=after(150),
        max_attempts=2,
    )
    w.service.recover()
    assert root(w)["status"] == "CRAWLING_AND_PARSING"
    w.queue.send_json.assert_not_called()


def test_generation_send_failure_remains_recoverable(workflow):
    w = workflow
    w.generation.send_json.side_effect = SQSClientError("unavailable")
    with pytest.raises(SQSClientError):
        w.service.process_message(w.message)
    assert w.runs.get(site_id="site", crawl_run_id="run")["generation_dispatch_pending"]
    w.generation.send_json.side_effect = None
    w.service.recover()
    assert not w.runs.get(site_id="site", crawl_run_id="run")["generation_dispatch_pending"]
    w.fetch.assert_called_once()


def test_root_dispatch_gap_is_recovered(workflow):
    w = workflow
    w.service.recover()
    assert w.queue.send_json.call_args.args[0] == w.message


def test_child_dispatch_gap_is_recovered_even_if_parent_failed(workflow):
    w = workflow
    parent = claim(w)
    parent["children_root_url"] = parent["root_url"]
    w.queue.send_json.side_effect = SQSClientError("unavailable")
    with pytest.raises(SQSClientError):
        w.service._register_children(parent, "worker", ["https://example.com/child"])
    w.pages.finish(parent, token="worker", now=now(), error="failed")
    w.queue.send_json.side_effect = None
    w.service.recover()
    assert w.queue.send_json.call_args.args[0]["payload"]["url"].endswith("/child")
    w.generation.send_json.assert_not_called()


def test_unchanged_content_reuses_objects_but_rediscovers_links(workflow):
    w = workflow
    w.service.process_message(w.message)
    old_writes = list(w.s3.writes)
    message = w.setup.prepare(
        site_id="site", root_url="https://example.com/", crawl_run_id="second", timestamp=now()
    )
    w.service.process_message(message)
    assert w.s3.writes == old_writes
    assert w.pages.list_for_run("second")[0]["raw_html_hash"] == root(w)["raw_html_hash"]


def test_expired_discovery_lock_can_be_replaced(workflow):
    w = workflow
    assert w.runs.acquire_discovery_lock(
        site_id="site",
        crawl_run_id="run",
        token="old",
        now=now(),
        expires_at="2000-01-01T00:00:00+00:00",
    )
    assert w.runs.acquire_discovery_lock(
        site_id="site", crawl_run_id="run", token="new", now=now(), expires_at=after(30)
    )
    w.runs.release_discovery_lock(site_id="site", crawl_run_id="run", token="old")
    assert w.runs.get(site_id="site", crawl_run_id="run")["discovery_lock_token"] == "new"


def test_no_generation_while_worker_holds_discovery_lock(workflow):
    w = workflow
    p = claim(w)
    w.runs.acquire_discovery_lock(
        site_id="site", crawl_run_id="run", token="discovery", now=now(), expires_at=after(30)
    )
    w.pages.finish(p, token="worker", now=now())
    w.service.check_generation({"site_id": "site", "crawl_run_id": "run"})
    w.generation.send_json.assert_not_called()


def test_markdown_can_be_fetched_and_parsed(workflow):
    w = workflow
    w.fetch.return_value = FetchedPage(
        b"# Example\n\nHello!", "text/markdown", "https://example.com/", 200
    )
    w.service.process_message(w.message)
    assert root(w)["status"] == "COMPLETED"
    assert root(w)["raw_html_s3_key"].endswith(".md")


def test_terminal_record_cannot_be_reclaimed(workflow):
    w = workflow
    w.service.process_message(w.message)
    assert not w.pages.claim(
        root(w),
        runs_table_name="runs",
        token="duplicate",
        now=now(),
        expires_at=after(150),
        max_attempts=2,
    )


def test_cross_site_message_cannot_claim_page(workflow):
    w = workflow
    w.message["payload"]["site_id"] = "different"
    with pytest.raises(ValueError):
        w.service.process_message(w.message)
    w.fetch.assert_not_called()


def test_duplicate_setup_rolls_back_site_pointer_update(workflow):
    w = workflow
    original = w.sites.get("site")
    with pytest.raises(DynamoDBConditionNotMetError):
        w.setup.prepare(
            site_id="site",
            root_url="https://example.com/",
            crawl_run_id="run",
            timestamp=after(60),
        )
    assert w.sites.get("site") == original
    assert len(w.pages.list_for_run("run")) == 1


def test_recovery_cannot_fail_a_page_from_a_stale_pre_parse_snapshot(workflow):
    w = workflow
    old = claim(w)
    w.pages.save_result(
        old, token="worker", now=now(), result={"parsed_content_s3_key": "parsed/result.json"}
    )
    expire(w, old)
    assert not w.pages.fail_abandoned(old, now=now(), error="stale recovery")
    assert root(w)["status"] == "CRAWLING_AND_PARSING"


def test_retry_replays_site_update_after_raw_checkpoint(workflow, monkeypatch):
    w = workflow
    original = w.sites.mark_content_changed
    update = Mock(side_effect=[RuntimeError("interrupted site update"), None])
    monkeypatch.setattr(w.sites, "mark_content_changed", update)
    w.service.process_message(w.message)
    assert root(w)["raw_html_changed"]
    assert not w.sites.get("site").get("modified_at")
    expire(w, root(w))
    monkeypatch.setattr(w.sites, "mark_content_changed", original)
    w.service.process_message(w.message)
    assert root(w)["status"] == "COMPLETED"
    assert w.sites.get("site")["modified_at"] == root(w)["crawled_at"]
    w.fetch.assert_called_once()


def test_generator_failure_is_atomic_and_idempotent(workflow):
    w = workflow
    w.service.process_message(w.message)
    args = dict(
        site_id="site", crawl_run_id="run", error_message="Bedrock failed", updated_at=now()
    )
    assert w.runs.mark_generation_failed(**args)
    failed = w.runs.get(site_id="site", crawl_run_id="run")
    assert failed["status"] == "FAILED"
    assert failed["error_message"] == "Bedrock failed"
    assert "generation_dispatch_pending" not in failed
    assert not w.runs.mark_generation_failed(**{**args, "error_message": "duplicate"})
    assert w.runs.get(site_id="site", crawl_run_id="run") == failed


def test_generator_failure_cannot_overwrite_completed_or_create_missing_run(workflow):
    w = workflow
    w.service.process_message(w.message)
    w.runs.mark_generation_completed(
        site_id="site",
        crawl_run_id="run",
        version_id="version",
        crawl_content_hash="hash",
        generated_at=now(),
    )
    completed = w.runs.get(site_id="site", crawl_run_id="run")
    for run_id in ["run", "missing"]:
        assert not w.runs.mark_generation_failed(
            site_id="site",
            crawl_run_id=run_id,
            error_message="late failure",
            updated_at=now(),
        )
    assert w.runs.get(site_id="site", crawl_run_id="run") == completed
    assert w.runs.get(site_id="site", crawl_run_id="missing") is None
