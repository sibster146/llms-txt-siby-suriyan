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

## Development S3

The development configuration creates a private, encrypted, versioned `dev-llms-txt-s3-<account-id>` bucket for raw HTML, parsed Markdown, and generated `llms.txt` files. Its `Name` tag is `dev_llms_txt_s3`. The account ID keeps the globally scoped bucket name unique.

## GitHub Actions deployment

Pushes to `feature/**` and `dev` run `.github/workflows/deploy-dev-infrastructure.yml`. The workflow:

1. Assumes the AWS deployment role through GitHub OIDC.
2. Creates the encrypted, versioned development state bucket if it does not exist.
3. Initializes Terraform with S3 state and native state locking.
4. Validates, plans, and applies `infrastructure/dev`.
5. Writes the Cognito pool and web-client IDs to the workflow summary.

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
