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

The development configuration creates three encrypted queues:

- `dev_llms_txt_crawl_sqs`
- `dev_llms_txt_parse_sqs`
- `dev_llms_txt_llm_txt_sqs`

All queues use long polling and retain messages for four days. The generator queue uses a
30-minute visibility timeout so a Bedrock request can finish before SQS makes the message
available again. Each workflow queue has its own dead-letter queue.

## Development S3

The development configuration creates a private, encrypted, versioned `dev-llms-txt-s3-<account-id>` bucket for raw HTML, parsed Markdown, and generated `llms.txt` files. Its `Name` tag is `dev_llms_txt_s3`. The account ID keeps the globally scoped bucket name unique.

## Development web crawler

The web crawler is deployed as the `dev_llms_txt_web_crawler` Lambda using an image in the immutable `dev_llms_txt_web_crawler` ECR repository. It consumes one crawl message per invocation, stores raw HTML under the S3 `raw/` prefix, updates the crawl-pages table, and publishes successful downloads to the parse queue. Its execution role is limited to those resources.

## Development HTML parser

The parser is deployed as the `dev_llms_txt_html_parser` Lambda using an image in the immutable `dev_llms_txt_html_parser` ECR repository. It consumes the parse queue, stores changed page content under the S3 `parsed/` prefix, rediscovers same-site child links, and publishes those links to the crawl queue. When every page in a crawl is terminal, it publishes the run to the `llm_txt` queue.

## Development llms.txt generator

The generator is deployed as the `dev_llms_txt_generator` Lambda using an image
in the matching ECR repository. It consumes `llm_txt_sqs`, reads parsed crawl content,
and asks Moonshot AI Kimi K3 to produce the complete `llms.txt`. The model response is
stored unchanged without output validation or deterministic fallback. Generated files are
stored under `llms-txt/{site_id}/{version_id}/llms.txt`, and the corresponding DynamoDB
site, crawl-run, and version records are updated after the object has been written.

## Development nightly refresh

EventBridge Scheduler invokes `dev_llms_txt_nightly_refresh` every day at 3:00 AM in
`America/New_York`. The Lambda scans the Sites table and queues a fresh root crawl for
every registered site. The schedule uses deterministic crawl-run IDs so EventBridge
retries do not create duplicate runs. Daylight-saving changes are handled by the schedule
timezone rather than a fixed UTC offset.

## Parser duplicate protection

Before parsing, a worker atomically transitions the page identified by its crawl-run ID
and canonical URL hash to `PARSING`. If another worker already holds an unexpired parsing
lease, the duplicate delivery exits without writing parsed content or updating crawl
counts. An expired lease can be reclaimed after a worker crashes or times out.

## GitHub Actions deployment

Pushes to `feature/**` and `dev` run `.github/workflows/deploy-dev-infrastructure.yml`. The workflow:

1. Assumes the AWS deployment role through GitHub OIDC.
2. Creates the encrypted, versioned development state bucket if it does not exist.
3. Initializes Terraform with S3 state and native state locking.
4. Provisions all four Lambda ECR repositories in a targeted bootstrap apply.
5. Builds the crawler, parser, generator, and nightly refresh images and pushes them with the Git commit SHA as their immutable tag.
6. Plans and applies the complete development infrastructure using that image.
7. Writes Cognito and Lambda deployment details to the workflow summary.

The GitHub `dev` environment must define:

- `AWS_REGION`
- `AWS_DEPLOY_ROLE_ARN`

Parser behavior and capacity are controlled by Terraform variables in
`infrastructure/dev/variables.tf`:

- `parser_max_attempts` (default: `2`, one initial attempt and one retry)
- `parser_retry_delay_seconds` (default: `30`)
- `parser_max_depth` (default: `2`)
- `parser_max_discovered_pages` (default: `1000`, including the root page)
- `parser_max_links_per_page` (default: `100`)
- `parser_maximum_concurrency` (default: `25`)
- `parser_memory_size` (default: `2048` MB)

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

- `nightly_refresh_schedule_expression` (default: `cron(0 3 * * ? *)`)
- `nightly_refresh_schedule_timezone` (default: `America/New_York`)

Attach the permissions in `github-actions-dev-policy.json` to that deployment role. The state bucket is named `dev-llms-txt-<account-id>-terraform-state`; S3 bucket names cannot contain underscores, so this is the AWS-required exception to the resource naming convention.

## Production deployment

Pushes to `prod` run `.github/workflows/deploy-prod.yml`. The production workflow uses
the same crawler, parser, generator, and nightly-refresh pipeline with `prod_` resource
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
