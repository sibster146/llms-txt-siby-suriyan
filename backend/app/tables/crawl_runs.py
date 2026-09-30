import contextlib
from typing import Any

from boto3.dynamodb.conditions import Attr

from app.clients.dynamodb import DynamoDBClient, DynamoDBConditionNotMetError


class CrawlRunsTable:
    """Run lifecycle, discovery lock, and durable generation dispatch."""

    def __init__(self, dynamodb: DynamoDBClient) -> None:
        """Bind the CrawlRuns client during API or Lambda dependency setup.

        The supplied client targets the environment's run table. Construction
        performs no reads or writes.
        """
        self.dynamodb = dynamodb

    @staticmethod
    def new_item(*, site_id: str, crawl_run_id: str, created_at: str, root_url: str) -> dict:
        """Build, but do not persist, a PENDING run with its URL and timestamps.

        Used by CrawlSetupService for manual and nightly crawls. The returned
        dictionary is committed with the site update and root page by
        CrawlPagesTable.initialize_run. site_id and crawl_run_id form its key.
        """
        return dict(
            site_id=site_id,
            crawl_run_id=crawl_run_id,
            created_at=created_at,
            updated_at=created_at,
            root_url=root_url,
            status="PENDING",
        )

    def get(self, *, site_id: str, crawl_run_id: str) -> dict[str, Any] | None:
        """Read one run by its complete key, returning None if it is absent.

        Uses a strongly consistent read. API status/detail routes and workers
        use this to inspect progress, decide eligibility, and resume existing work.
        """
        return self.dynamodb.get_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id), consistent_read=True
        )

    def list_active(self) -> list[dict[str, Any]]:
        """Scan for PENDING, CRAWLING_AND_PARSING, or GENERATING runs.

        Periodic crawl recovery uses these records to find stranded page work
        and unsent generation messages. The client paginates the scan with
        strongly consistent reads; this is not a transactional table snapshot.
        """
        return self.dynamodb.scan(
            Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING", "GENERATING"]),
            ConsistentRead=True,
        )

    def acquire_discovery_lock(
        self, *, site_id: str, crawl_run_id: str, token: str, now: str, expires_at: str
    ) -> bool:
        """Acquire an absent or expired run discovery lock for the given token.

        Used before registering child batches and checking generation readiness,
        so those operations cannot proceed under competing valid lock owners.
        now and expires_at are comparable UTC ISO timestamps supplied by the caller.
        Only PENDING or CRAWLING_AND_PARSING runs qualify.

        Returns True on acquisition, False on a failed condition. Other database
        failures propagate. Callers must verify ownership again in protected writes.
        """
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET discovery_lock_token = :token, discovery_lock_expires_at = :expiry"
                ),
                expression_attribute_values={":token": token, ":expiry": expires_at},
                condition_expression=(
                    Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                    & (
                        Attr("discovery_lock_expires_at").not_exists()
                        | Attr("discovery_lock_expires_at").lte(now)
                    )
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def release_discovery_lock(self, *, site_id: str, crawl_run_id: str, token: str) -> None:
        """Remove the discovery lock only if its stored token still matches.

        Called in finally blocks after child registration or readiness checks.
        A missing/replaced lock is a harmless no-op; other database errors
        propagate. An expired owner cannot release a replacement owner's lock.
        """
        with contextlib.suppress(DynamoDBConditionNotMetError):
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression="REMOVE discovery_lock_token, discovery_lock_expires_at",
                condition_expression=Attr("discovery_lock_token").eq(token),
            )

    def claim_generation(
        self, *, site_id: str, crawl_run_id: str, token: str, updated_at: str
    ) -> bool:
        """Transition a locked crawl to GENERATING and flag its message as unsent.

        check_generation calls this after finding every page terminal and at
        least one successful page. This method does not inspect pages itself.
        The write requires a crawling/pending run, the matching discovery token,
        and a lease valid at updated_at; it removes the lock in the same update.

        Returns False if a condition fails, otherwise True. The caller sends
        the SQS message afterward; generation_dispatch_pending enables recovery
        if that separate send fails. Other database failures propagate.
        """
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET #s = :generating, generation_dispatch_pending = :yes, updated_at = :now "
                    "REMOVE discovery_lock_token, discovery_lock_expires_at"
                ),
                expression_attribute_names={"#s": "status"},
                expression_attribute_values={
                    ":generating": "GENERATING",
                    ":yes": True,
                    ":now": updated_at,
                },
                condition_expression=(
                    Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                    & Attr("discovery_lock_token").eq(token)
                    & Attr("discovery_lock_expires_at").gt(updated_at)
                ),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True

    def mark_generation_sent(self, *, site_id: str, crawl_run_id: str) -> None:
        """Clear generation_dispatch_pending after a successful generator SQS send.

        Used by normal readiness checks and periodic recovery. Only a GENERATING
        run is updated; a condition failure is ignored if it has moved on.
        This records transport success, not completion of generation, and does
        not make the SQS send and DynamoDB update atomic.
        """
        with contextlib.suppress(DynamoDBConditionNotMetError):
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression="SET generation_dispatch_pending = :no",
                expression_attribute_values={":no": False},
                condition_expression=Attr("status").eq("GENERATING"),
            )

    def fail_empty_run(
        self, *, site_id: str, crawl_run_id: str, token: str, updated_at: str
    ) -> None:
        """Fail a crawl whose pages all failed and remove its discovery lock.

        check_generation calls this after inspecting a nonempty set of terminal
        pages with no successes. The method does not count pages itself. It
        requires the matching unexpired token and a pending/crawling run at
        updated_at; a rejected condition raises DynamoDBConditionNotMetError.
        Stores an explanatory error so generation is not attempted.
        """
        self.dynamodb.update_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
            update_expression=(
                "SET #s = :failed, updated_at = :now, error_message = :error "
                "REMOVE discovery_lock_token, discovery_lock_expires_at"
            ),
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":failed": "FAILED",
                ":now": updated_at,
                ":error": "No pages could be crawled and parsed successfully",
            },
            condition_expression=(
                Attr("status").is_in(["PENDING", "CRAWLING_AND_PARSING"])
                & Attr("discovery_lock_token").eq(token)
                & Attr("discovery_lock_expires_at").gt(updated_at)
            ),
        )

    def mark_generation_completed(
        self,
        *,
        site_id: str,
        crawl_run_id: str,
        version_id: str,
        crawl_content_hash: str,
        generated_at: str,
    ) -> None:
        """Record the selected llms.txt version and mark the run COMPLETED.

        The generator calls this after persisting a new version or selecting an
        existing version for unchanged content. version_id links to that version;
        crawl_content_hash identifies the crawl's content manifest. generated_at
        is stored as both generated_at and updated_at, and dispatch state is removed.

        GENERATING and COMPLETED runs are accepted so completion can be replayed.
        Other states or missing runs raise DynamoDBConditionNotMetError. Replays
        write the supplied values; this does not enforce an immutable version ID.
        """
        self.dynamodb.update_item(
            key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
            update_expression=(
                "SET #s = :status, llms_txt_version_id = :version, "
                "crawl_content_hash = :hash, generated_at = :now, updated_at = :now "
                "REMOVE generation_dispatch_pending"
            ),
            expression_attribute_names={"#s": "status"},
            expression_attribute_values={
                ":status": "COMPLETED",
                ":version": version_id,
                ":hash": crawl_content_hash,
                ":now": generated_at,
            },
            condition_expression=Attr("status").is_in(["GENERATING", "COMPLETED"]),
        )

    def mark_generation_failed(
        self, *, site_id: str, crawl_run_id: str, error_message: str, updated_at: str
    ) -> bool:
        """Mark exhausted generation FAILED when handling a generator DLQ message.

        Store error_message truncated to 1,000 characters and updated_at, removing
        generation_dispatch_pending. Only a GENERATING run may transition.

        Returns True when updated and False for a rejected condition, including
        missing or already-terminal runs. Other database errors propagate so the
        DLQ message can be retried rather than silently losing the failure update.
        """
        try:
            self.dynamodb.update_item(
                key=dict(site_id=site_id, crawl_run_id=crawl_run_id),
                update_expression=(
                    "SET #s = :failed, error_message = :error, updated_at = :now "
                    "REMOVE generation_dispatch_pending"
                ),
                expression_attribute_names={"#s": "status"},
                expression_attribute_values={
                    ":failed": "FAILED",
                    ":error": error_message[:1000],
                    ":now": updated_at,
                },
                condition_expression=Attr("status").eq("GENERATING"),
            )
        except DynamoDBConditionNotMetError:
            return False
        return True
