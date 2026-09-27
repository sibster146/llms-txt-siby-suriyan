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

All queues use long polling, retain messages for four days, and have a five-minute visibility timeout.
The crawl and parser queues move failed messages to their respective dead-letter queues after five receives.

## Development S3

The development configuration creates a private, encrypted, versioned `dev-llms-txt-s3-<account-id>` bucket for raw HTML, parsed Markdown, and generated `llms.txt` files. Its `Name` tag is `dev_llms_txt_s3`. The account ID keeps the globally scoped bucket name unique.

## Development web crawler

The web crawler is deployed as the `dev_llms_txt_web_crawler` Lambda using an image in the immutable `dev_llms_txt_web_crawler` ECR repository. It consumes one crawl message per invocation, stores raw HTML under the S3 `raw/` prefix, updates the crawl-pages table, and publishes successful downloads to the parse queue. Its execution role is limited to those resources.

## Development HTML parser

The parser is deployed as the `dev_llms_txt_html_parser` Lambda using an image in the immutable `dev_llms_txt_html_parser` ECR repository. It consumes the parse queue, stores changed page content under the S3 `parsed/` prefix, rediscovers same-site child links, and publishes those links to the crawl queue. When every page in a crawl is terminal, it publishes the run to the `llm_txt` queue.

## GitHub Actions deployment

Pushes to `feature/**` and `dev` run `.github/workflows/deploy-dev-infrastructure.yml`. The workflow:

1. Assumes the AWS deployment role through GitHub OIDC.
2. Creates the encrypted, versioned development state bucket if it does not exist.
3. Initializes Terraform with S3 state and native state locking.
4. Provisions both Lambda ECR repositories in a targeted bootstrap apply.
5. Builds the crawler and parser images and pushes them with the Git commit SHA as their immutable tag.
6. Plans and applies the complete development infrastructure using that image.
7. Writes Cognito, crawler, and parser deployment details to the workflow summary.

The GitHub `dev` environment must define:

- `AWS_REGION`
- `AWS_DEPLOY_ROLE_ARN`

Attach the permissions in `github-actions-dev-policy.json` to that deployment role. The state bucket is named `dev-llms-txt-<account-id>-terraform-state`; S3 bucket names cannot contain underscores, so this is the AWS-required exception to the resource naming convention.

For local validation without applying infrastructure:

```bash
terraform fmt -check -recursive infrastructure
terraform -chdir=infrastructure/dev init -backend=false
terraform -chdir=infrastructure/dev validate
```
