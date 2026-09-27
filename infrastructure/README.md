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
