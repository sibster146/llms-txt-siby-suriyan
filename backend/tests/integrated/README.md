# Live workflow test

This opt-in test uses real AWS resources and model calls, not mocks. Both deployment
workflows run it after provisioning. Dev starts FastAPI in a subprocess on the runner;
prod uses the deployed CloudFront HTTPS endpoint after ECS becomes stable.

Job order:
- Dev: Create Infrastructure -> Run Integration Tests.
- Prod: Create Infrastructure -> Deploy Backend -> Deploy Frontend -> Run Integration Tests.

Each job authenticates to AWS independently. Infrastructure outputs are passed as a
one-day GitHub artifact, so downstream jobs do not need to initialize Terraform.
The infrastructure job builds the backend image before Terraform references it;
Deploy Backend explicitly rolls out the resulting task definition and checks ECS
stability. Deploy Frontend waits for CloudFront invalidation before tests start.

The test signs in through `POST /auth/guest`, submits `https://www.roblox.com/`, and
polls the returned crawl ID every four seconds for up to 20 minutes. It passes only
when the run is COMPLETED, all pages are terminal, at least one page succeeded, and
the generated version can be retrieved with nonempty content and a matching hash.
A FAILED run or timeout fails the deployment test. Individual failed pages are allowed.
Roblox is a live third-party dependency: blocking, robots rules, or downtime can fail
the test even if deployment itself succeeded. This test does not bypass those controls.

## Credentials and configuration

- Add `GUEST_EMAIL` and `GUEST_PASSWORD` to the GitHub **dev environment secrets**.
  They must match the existing confirmed dev Cognito guest account.
- Prod uses its already-configured guest endpoint and backend secrets; the test runner
  does not need the production password.
- Resource names, bucket, Cognito IDs, queue URL, and production URL come from Terraform
  outputs. The deployment role needs its existing scoped DynamoDB/S3 data permissions
  and Lambda configuration-read access.
- `INTEGRATION_TIMEOUT_SECONDS` optionally overrides the 1,200-second poll deadline.
- Regular pytest runs skip this suite unless `RUN_INTEGRATION_TESTS=1`.

Run separately from `tests/mock` so its environment fixtures cannot affect configuration.
With Terraform initialized and application environment variables exported, invoke from
the repository root using a Python environment containing `backend[dev]`:

```bash
bash infrastructure/scripts/run-integration-tests.sh dev
```

## Cleanup and safety

Roblox is reserved for tests in each environment. The test refuses to start if that
site already has records or stored files, and conditionally reserves its site record.
It never deletes the guest account, purges shared queues, or empties application buckets.

Fixture teardown runs after success, failure, or timeout. It marks unfinished test
runs FAILED, removes their discovery locks, then waits the longest deployed worker
timeout plus ten seconds for in-flight work to stop. It removes that test's pages,
run, generated versions, guest mapping, site record, and site-scoped S3 objects,
including historical object versions and delete markers. This wait also occurs on
success to account for overlapping invocations. Remaining queue deliveries cannot
recreate a deleted crawl; they are handled by the existing workers/retry/DLQ behavior.

If another user or crawl touches the site, cleanup fails and retains data rather than
delete shared work. Do not manually refresh Roblox or run the nightly refresh during
this test. An abruptly cancelled/killed CI runner cannot guarantee teardown; retained
data blocks the next test and must be inspected before removal. CI keeps its JUnit
report, and the console prints the crawl ID/statuses but never guest credentials/tokens.
