# Infrastructure

Terraform configurations are separated by environment. Reusable resources belong in `modules`; environment-specific composition and values belong in `dev` or `prod`.

## Resource naming

Every named AWS resource begins with its environment:

- Development: `dev_`
- Production: `prod_`

## Development Cognito

The development configuration creates:

- An email-based Cognito user pool with optional TOTP MFA
- Admin-created users; the backend will mark `email_verified` as `true`
- A public web client for direct SRP authentication from the custom frontend

No Cognito domain or managed login UI is created. The application owns the sign-in, sign-out, and forgot-password pages. Cognito sends password-reset codes to users whose backend-created accounts have `email_verified` set to `true`.

## Development DynamoDB

The development configuration creates on-demand tables for:

- Sites
- User-to-site mappings
- Crawl runs
- Pages processed during each crawl
- Generated `llms.txt` versions

Development table names begin with `dev_llms_txt_`. Point-in-time recovery and deletion protection are disabled in development and can be enabled when the module is used by production.

## Development SQS

The development configuration creates two encrypted queues:

- `dev_llms_txt_crawl_sqs`
- `dev_llms_txt_llm_txt_sqs`

All queues use long polling and retain messages for four days. The generator queue uses a
30-minute visibility timeout so a Bedrock request can finish before SQS makes the message
available again. Each workflow queue has its own dead-letter queue.

## Development S3

The development configuration creates a private, encrypted, versioned `dev-llms-txt-s3-<account-id>` bucket for raw HTML/Markdown, parsed JSON, and generated `llms.txt` files. Its `Name` tag is `dev_llms_txt_s3`. The account ID keeps the globally scoped bucket name unique.

## Combined crawl-and-parse worker

The existing `dev_llms_txt_web_crawler` and `prod_llms_txt_web_crawler` Lambdas now
fetch and parse one page per invocation. HTML, Markdown, robots.txt, safe URL checks,
depth limits, and sitemap discovery use the existing extraction helpers.

Flow: `crawl_sqs -> combined worker -> llm_txt_sqs -> generator`.
There is no parser Lambda, parser image build, parse queue, or parse DLQ.
The old parser ECR repository is retained so deployment does not attempt to delete
a nonempty repository or historical images.

Page states: `QUEUED -> CRAWLING_AND_PARSING -> COMPLETED | FAILED`.
Run states: `PENDING -> CRAWLING_AND_PARSING -> GENERATING -> COMPLETED | FAILED`.
Pages never move backwards. A retry retains the working state.

Each page has a fenced `worker_token`, `lease_expires_at`, and `attempt_count`.
The lease exceeds the Lambda timeout by 30 seconds. Duplicate active messages do
not consume processing attempts. Caught retryable failures persist `retry_after`
and dispatch a delayed message for 30 seconds later. Two actual attempts are allowed;
404s, oversized responses, unsafe URLs, unsupported content, and robots denial fail
without a retry. A timeout is recovered after its lease expires, not exactly 30 seconds later.
If parsing has already succeeded, retrying child registration/dispatch does not consume
another fetch/parse attempt.

A short `discovery_lock_token` / `discovery_lock_expires_at` pair on CrawlRuns
serializes child registration. Under that lock, the worker queries all existing pages,
deduplicates URLs, and inserts only children that fit the cap (including the root).
Each transaction checks both the run lock and parent ownership. Network fetches and
SQS sends occur outside the lock. The parent stays active until child dispatch finishes.

No discovered/completed/failed/pending counters are stored on CrawlRuns. API responses
derive these counts by querying CrawlPages with consistent reads and pagination.
The completion check uses the discovery lock to prevent inserts while it checks for
active pages. Only one conditional transition to GENERATING succeeds.
If every page failed, the run becomes FAILED without sending a generation message.

Raw and parsed content use content-addressed keys. Unchanged content reuses objects,
but child links are always extracted from the current raw content.
Page `dispatch_pending` / `dispatch_after` and run `generation_dispatch_pending`
preserve queue-send intent. Sends happen before acceptance is recorded: duplicates are
possible, but failed sends cannot silently abandon work.

An EventBridge recovery schedule invokes the same worker every two minutes with
`{"action":"recover_crawls"}`. It resends abandoned/unsent page work, fails expired final
attempts, and retries generation readiness/dispatch. The crawl DLQ uses the same ownership
and actual-attempt rules; SQS receive counts are not treated as processing attempts.
Recovery errors are logged with the run ID for retry on the next sweep.

Normal crawl SQS mappings allow three concurrent invocations per environment;
generator mappings allow two. The crawl DLQ has its own limit of two. Recovery and nightly invocations
also share account capacity; these are queue limits, not global reservations.
The generator DLQ also has a separate concurrency limit of two.
Crawl queue visibility is six times the combined worker timeout (default 720 seconds).
Caught failures use delayed messages or a 30-second visibility change.

## Deploying this transition

Drain or intentionally clear old workflow queues and active crawl records before deploying.
Old page states and parser messages are not compatible with the new worker. Terraform
will remove the parser Lambda, its role/log group, the parse queue, and the parse DLQ.
Review that destruction in the GitHub Actions plan. Deploy the API, combined worker,
nightly refresh, and generator images together. Do not reuse legacy in-progress runs.

## Development llms.txt generator

The generator is deployed as the `dev_llms_txt_generator` Lambda using an image
in the matching ECR repository. It consumes `llm_txt_sqs`, reads parsed crawl content,
and asks Moonshot AI Kimi K3 to produce the complete `llms.txt`. The model response is
stored unchanged without output validation or deterministic fallback. Generated files are
stored under `llms-txt/{site_id}/{version_id}/llms.txt`, and the corresponding DynamoDB
site, crawl-run, and version records are updated after the object has been written.

The generator Lambda also consumes `llm_txt_dlq` without invoking the model. It
atomically marks a GENERATING run FAILED and saves the failure reason; completed
runs are never overwritten. A failed database write leaves the DLQ message available
for retry. Messages without valid run identifiers are logged and retained for manual
investigation until their retention expires.

## Development nightly refresh

EventBridge Scheduler invokes `dev_llms_txt_nightly_refresh` every day at 2:00 AM in
`America/New_York`. The Lambda scans the Sites table and queues a fresh root crawl for
every registered site. The schedule uses deterministic crawl-run IDs so EventBridge
retries do not create duplicate runs. Daylight-saving changes are handled by the schedule
timezone rather than a fixed UTC offset.

Manual and scheduled crawl setup atomically write `Sites.latest_crawl_run_id`,
the run, and the root page in one transaction. The homepage and file-detail APIs use this pointer
to return the latest status, even if page content has not changed or another user
started the crawl. `UserSites` remains the access-control mapping;
`Sites.last_crawl_run_id` retains its existing content-change meaning. Both pages
fetch their API on opening and poll active runs every four seconds until completion
or failure. Site and run lookups use strongly consistent DynamoDB reads.

## GitHub Actions deployment

Pushes to `feature/**` and `dev` run `.github/workflows/deploy-dev-infrastructure.yml`. The workflow:

1. Assumes the AWS deployment role through GitHub OIDC.
2. Creates the encrypted, versioned development state bucket if it does not exist.
3. Initializes Terraform with S3 state and native state locking.
4. Provisions the three active Lambda ECR repositories in a targeted bootstrap apply.
5. Builds the combined worker, generator, and nightly refresh images and pushes them with the Git commit SHA as a mutable deployment tag.
6. Plans and applies the complete development infrastructure using that image.
7. Writes Cognito and Lambda deployment details to the workflow summary.

The GitHub `dev` environment must define:

- `AWS_REGION`
- `AWS_DEPLOY_ROLE_ARN`

Combined worker behavior and capacity are controlled by Terraform variables in
`infrastructure/dev/variables.tf`:

- `crawler_max_attempts` (default: `2`, one initial attempt and one retry)
- `crawler_retry_delay_seconds` (default: `30`)
- `crawler_max_depth` (default: `2`)
- `crawler_max_discovered_pages` (default: `500`, including the root page)
- `crawler_max_links_per_page` (default: `100`)
- `crawler_maximum_concurrency` (default: `3`)
- `crawler_memory_size` (default: `2048` MB)
- `crawler_timeout_seconds` (default: `120` seconds)

The following Terraform variables control generator behavior and capacity:

- `generator_model_id` (default: `us.moonshotai.kimi-k3`)
- `generator_max_input_pages` (default: `500`)
- `generator_max_output_links` (default: `30`)
- `generator_max_excerpt_chars` (default: `1000`)
- `generator_max_model_tokens` (default: `4000`)
- `generator_maximum_concurrency` (default: `2`)
- `generator_memory_size` (default: `1024` MB)
- `generator_timeout_seconds` (default: `300`)

The nightly schedule is controlled by Terraform variables:

- `nightly_refresh_schedule_expression` (default: `cron(0 2 * * ? *)`)
- `nightly_refresh_schedule_timezone` (default: `America/New_York`)

Attach the permissions in `github-actions-dev-policy.json` to that deployment role. The state bucket is named `dev-llms-txt-<account-id>-terraform-state`; S3 bucket names cannot contain underscores, so this is the AWS-required exception to the resource naming convention.

## Production deployment

Pushes to `prod` run `.github/workflows/deploy-prod.yml`. The production workflow uses
the same combined worker, generator, and nightly-refresh pipeline with `prod_` resource
names. It additionally:

1. Builds the FastAPI backend and runs it as an ECS Fargate service behind an application load balancer.
2. Creates a private S3 bucket for the compiled React application.
3. Creates one CloudFront distribution that serves React and proxies API paths to FastAPI.
4. Builds React with the Terraform-managed Cognito IDs and AWS-provided CloudFront URL.
5. Uploads the build to S3 and invalidates the CloudFront distribution.

The load balancer accepts origin traffic only from the AWS-managed CloudFront prefix list.
Fargate tasks accept port `8000` only from the load balancer security group. Production
DynamoDB tables use point-in-time recovery and deletion protection; Cognito and the load
balancer also use deletion protection.

Create a GitHub environment named `prod` with `AWS_REGION` and
`AWS_DEPLOY_ROLE_ARN`. Add `GUEST_EMAIL` and `GUEST_PASSWORD` as GitHub environment
secrets, and attach `github-actions-prod-policy.json` to that OIDC role.
All application configuration is resolved from Terraform; no Cognito IDs, resource names,
bucket names, queue URLs, or application URLs need to be copied into GitHub variables.
The workflow stores the guest credentials in Secrets Manager, creates the confirmed guest
account in the production Cognito pool, and injects the two values into ECS without placing
the password in the task definition or Terraform state.

The production state bucket is named
`prod-llms-txt-<account-id>-terraform-state`. The deployed URL is available in both the
workflow summary and the Terraform `application_url` output.

For local validation without applying infrastructure:

```bash
terraform fmt -check -recursive infrastructure
terraform -chdir=infrastructure/dev init -backend=false
terraform -chdir=infrastructure/dev validate

terraform -chdir=infrastructure/prod init -backend=false
terraform -chdir=infrastructure/prod validate
```
