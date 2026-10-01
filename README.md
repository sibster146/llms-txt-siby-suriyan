# llms-txt-siby-suriyan

Web application for generating and maintaining `llms.txt` files from website content.

## Table of Contents

- [How To Use](#how-to-use)
- [Host on Your Own Domain](#host-on-your-own-domain)
- [Project Structure](#project-structure)
- [Architecture and Workflow](#architecture-and-workflow)

## How To Use

1. Access the platform at [https://d6sr5c6k9nocz.cloudfront.net](https://d6sr5c6k9nocz.cloudfront.net).
2. Create an account and sign in, or select **Continue as a Guest**.
3. Click **New Website**, enter the website URL, and click **Create**.
4. Wait for the website to be crawled and its `llms.txt` file to be generated. Click the website tile to view the file.
5. Once the file is generated, click **Refresh** on its page to manually run the process again. A nightly refresh also checks registered websites automatically and regenerates their files when the crawl content changes.

## Host on Your Own Domain

Deploy your own copy into your AWS account using the steps below. You do **not** need to purchase or configure a domain: AWS assigns your deployment an HTTPS CloudFront URL. These instructions deploy the frontend, backend, workers, and data services, not just the frontend.

### 1. Prepare Your AWS Account

Use an AWS account you control with billing enabled and an administrator or bootstrap identity that can create IAM roles and an OpenID Connect provider. Use `us-east-1` to match the repository's defaults. Do not use the original project's AWS profile, deployment role, or application URL.

Install Git and the AWS CLI locally. Terraform is useful for checking configuration changes; Docker, Node.js, and Python builds run on GitHub-hosted runners during deployment. Configure your own AWS CLI credentials, then confirm the account:

```bash
aws sts get-caller-identity --profile YOUR_AWS_PROFILE
```

Expect AWS charges for ECS/Fargate, the load balancer, storage, requests, and Bedrock inference. Nightly refreshes also consume resources. Review your account's Lambda concurrency and Bedrock quotas, and set a billing budget before deploying.

### 2. Fork and Clone the Repository

Fork this repository into your GitHub account or organization, then clone **your fork**:

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/llms-txt-siby-suriyan.git
cd llms-txt-siby-suriyan
```

Ensure the branch you plan to deploy includes the current application, `infrastructure/`, `deployables/`, and `.github/workflows/` files. Open the fork's **Actions** tab and enable workflows if GitHub has disabled them. Forking does not copy the original repository's secrets or AWS access.

Production deploys from the `prod` branch. A separate development environment is optional; it is not required to host production.

### 3. Connect GitHub Actions to Your AWS Account

In AWS IAM, open **Identity providers** and add an **OpenID Connect** provider with provider URL `https://token.actions.githubusercontent.com` and audience `sts.amazonaws.com`. Reuse the provider if it already exists in your account.

Create an IAM role named `llms-txt-github-actions` using the following custom trust policy. Replace `YOUR_AWS_ACCOUNT_ID`, `YOUR_GITHUB_OWNER`, and `YOUR_REPOSITORY` with your own values. This permits only jobs from your fork's GitHub `prod` environment to assume the role. See [GitHub's AWS OIDC guide](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR_AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
          "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_OWNER/YOUR_REPOSITORY:environment:prod"
        }
      }
    }
  ]
}
```

Review [the production deployment policy](infrastructure/github-actions-prod-policy.json), then attach it to the role as an inline policy from the repository root:

```bash
aws iam put-role-policy \
  --profile YOUR_AWS_PROFILE \
  --role-name llms-txt-github-actions \
  --policy-name prod_llms_txt_terraform \
  --policy-document file://infrastructure/github-actions-prod-policy.json
```

The policy grants broad deployment permissions, including resource and IAM-role creation. Restrict who can change workflows or deploy from your repository. Bootstrap IAM setup is manual because the workflow needs the role before it can run Terraform. GitHub Actions uses short-lived OIDC credentials; do not add long-lived AWS access keys to the repository.

### 4. Configure the GitHub Production Environment

In your fork, open **Settings > Environments**, create an environment named **prod**, and restrict its deployment branches to `prod`. Add required reviewers if appropriate for your team.

Add these **environment variables**:

| Name | Value |
| --- | --- |
| `AWS_REGION` | `us-east-1` |
| `AWS_DEPLOY_ROLE_ARN` | `arn:aws:iam::YOUR_AWS_ACCOUNT_ID:role/llms-txt-github-actions` |

Add these **environment secrets**:

| Name | Value |
| --- | --- |
| `GUEST_EMAIL` | A valid email address for your deployment's shared guest account, without surrounding whitespace. |
| `GUEST_PASSWORD` | A unique password of at least 12 characters, including uppercase, lowercase, a number, and a symbol. |

You do not need to create the production guest account manually. The workflow creates it in Cognito, sets its permanent password, and stores the credentials in Secrets Manager for the backend. Guest sessions share the same account and website list; do not use a personal account's password for this feature.

### 5. Confirm Bedrock Access

Open Amazon Bedrock in `us-east-1` and verify that your account can invoke the model/inference profile configured as `generator_model_id` in [the production variables](infrastructure/prod/variables.tf). The repository currently specifies `us.moonshotai.kimi-k3`.

### 6. Review Deployment Configuration

Review [production Terraform variables](infrastructure/prod/variables.tf) for crawl limits, worker concurrency, backend capacity, model settings, and the nightly schedule. Defaults include a discovery cap of 500 pages, a depth of 2, and a nightly refresh at 2:00 AM in `America/New_York`.

Keep `project_name = "llms_txt"` for the initial deployment: workflow image names and deployment IAM policies rely on that naming convention. Keep the Terraform `aws_region` and GitHub `AWS_REGION` values aligned. Update the crawler user-agent repository link in `infrastructure/prod/main.tf` to identify your fork. Currently it is llms-txt-crawler/1.0 (+https://github.com/tryBaskt/llms-txt-siby-suriyan). Change the repo url to your own.

Commit configuration changes to your fork, either in the variable defaults or a non-secret `infrastructure/prod/terraform.tfvars`. Do not copy the example's placeholder `*_image_uri` values into an active tfvars file: GitHub Actions supplies the real image URIs, and tfvars values would override those environment inputs. Never commit credentials, `.env` files, or Terraform state.

After changing Terraform files, run `terraform fmt -recursive infrastructure` and include the formatting changes in your commit. The workflow checks formatting before deployment.

### 7. Deploy Production

Create a `prod` branch from the code you want to deploy if it does not exist, or update your existing `prod` branch. Push it to your fork:

```bash
git push origin prod
```

In **Actions**, open **Deploy Prod** and monitor these jobs in order:

1. **Create Infrastructure**: creates the remote state bucket and ECR repositories, builds/pushes images, provisions AWS resources, stores guest credentials, and configures the guest user.
2. **Deploy Backend**: rolls out the FastAPI ECS service and waits for a healthy deployment.
3. **Deploy Frontend**: builds React using Terraform outputs, uploads it to the private frontend S3 bucket, and invalidates CloudFront's cache.
4. **Run Integration Tests**: signs in as a guest, crawls the reserved test website `https://www.roblox.com/`, waits for generation, and cleans up that test's records and files.

The workflow creates its own account-specific Terraform state bucket. Do not point it at the original deployment's state or copy another account's state files. No production backend/frontend `.env` files or manually copied Cognito IDs are needed; configuration comes from Terraform outputs and Secrets Manager.

The integration test uses a live third-party website (https://www.roblox.com/) and real AWS/model calls. Reserve Roblox for the test rather than adding it through the UI. See [integration-test behavior and cleanup](backend/tests/integrated/README.md) before rerunning after an interrupted test.

### 8. Open and Verify Your Application

Find **Application** in the **Deploy Frontend** job summary. It will be your own `https://<distribution>.cloudfront.net` URL, also available as Terraform's `application_url` output.

Open that URL, try guest sign-in or create an account, and generate a file for a website other than the reserved integration-test site. Confirm that the status reaches completion, the file opens, and manual refresh works. In EventBridge Scheduler, confirm the production nightly-refresh and recovery schedules are enabled. CloudWatch logs contain worker errors if a crawl fails.

For subsequent releases, push changes to `prod` again. You can also rerun **Deploy Prod** manually when the workflow is available on your fork's default branch, selecting `prod` as the deployment branch. Never share the original application's CloudFront URL as the URL for your deployment.

### 9. Optional Development Environment

To provision development resources too, create a GitHub `dev` environment with the same variable/secret names, attach [the development deployment policy](infrastructure/github-actions-dev-policy.json) to an appropriate deployment role, and allow the exact OIDC subject `repo:YOUR_GITHUB_OWNER/YOUR_REPOSITORY:environment:dev` in that role's trust policy. Keep production's branch restrictions separate from development's `dev` and `feature/**` branches.

Push to `dev` or `feature/**` to run **Deploy Dev**. Development keeps React and FastAPI local while deploying Cognito, storage, queues, and workers in AWS. The dev integration test requires an existing confirmed guest Cognito user matching its secrets; unlike production, the dev workflow does not create that account. After the first infrastructure job completes, use the local setup below to create the dev guest through signup, or use the Cognito admin tools, then rerun the integration-test job. See [the infrastructure guide](infrastructure/README.md) for additional deployment details.

**Install dependencies and configure the environment**

Install Python 3.12, Node.js 22, and the AWS CLI. From the repository root, create a virtual environment, install the backend dependencies, and copy the example configuration files if you have not already created them:

```bash
python3.12 -m venv venv
source venv/bin/activate
python -m pip install -e 'backend[dev]'
cp -n backend/.env.example backend/.env
cp -n frontend/.env.example frontend/.env
```

Fill in `backend/.env` using the **dev** deployment's Terraform outputs. They are available in the infrastructure job's `terraform-outputs-dev` artifact immediately after deployment; its retention is one day. If you use Terraform locally, initialize it against your dev remote state before reading outputs.

| Backend variable | Value |
| --- | --- |
| `AWS_REGION` | Your dev deployment region, normally `us-east-1`. |
| `AWS_PROFILE_NAME` | Your own local AWS CLI profile with access to the dev resources. |
| `ENVIRONMENT` | `dev` |
| `PROJECT_NAME` | `llms_txt`, unless you changed the resource naming. |
| `APPLICATION_S3_BUCKET` | Terraform output `application_s3_bucket_name`. |
| `CRAWL_QUEUE_URL` | The `crawl` entry in Terraform output `sqs_queue_urls`. |
| `COGNITO_USER_POOL_ID` | Terraform output `cognito_user_pool_id`. |
| `COGNITO_APP_CLIENT_ID` | Terraform output `cognito_web_client_id`. |
| `GUEST_EMAIL` / `GUEST_PASSWORD` | The same guest credentials as your GitHub dev environment secrets. Both settings are required even before creating the guest account. |
| `CORS_ORIGINS` | `http://localhost:5173` |

Fill in `frontend/.env` with:

```dotenv
VITE_API_URL=http://localhost:8000
VITE_COGNITO_USER_POOL_ID=YOUR_DEV_USER_POOL_ID
VITE_COGNITO_USER_POOL_CLIENT_ID=YOUR_DEV_WEB_CLIENT_ID
```

Use the same Cognito pool and client IDs as the backend. Do not put AWS credentials or the guest password in the frontend environment; `VITE_` values are exposed to the browser. Keep both `.env` files out of Git.

**Terminal 1: start the backend**

From the repository root:

```bash
source venv/bin/activate
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run from `backend/` so the settings loader finds `backend/.env`. The API is available at [http://localhost:8000](http://localhost:8000), with interactive documentation at [http://localhost:8000/docs](http://localhost:8000/docs). If your AWS profile uses SSO, sign in with `aws sso login --profile YOUR_AWS_PROFILE` before making requests that access AWS.

**Terminal 2: start the frontend**

Open a second terminal at the repository root:

```bash
cd frontend
npm ci
npm run dev -- --host localhost --port 5173 --strictPort
```

Open [http://localhost:5173](http://localhost:5173). Create an account or use **Continue as a Guest** after the configured guest account exists. For the first dev setup, sign up using exactly the email and password configured in `GUEST_EMAIL` and `GUEST_PASSWORD` to create that account.

Keep both terminals running. The local backend sends crawl requests to the deployed dev queues; the AWS Lambda workers still perform crawling, parsing, and generation. Restart the frontend after changing its `.env`. If port 8000 or 5173 is occupied, stop the previous server or choose different ports and update `VITE_API_URL` and `CORS_ORIGINS` accordingly.

The project separates application logic from AWS entry points and infrastructure. React handles the user interface, FastAPI handles HTTP requests, and Lambda workers perform the asynchronous crawl and generation work.

## Project Structure

### Backend

The Python application lives in [`backend/app/`](backend/app). Its modules are shared by the FastAPI server and Lambda workers so that both use the same clients, table operations, and workflow logic.

| Module | Responsibility |
| --- | --- |
| [`main.py`](backend/app/main.py) | Creates the FastAPI application, configures CORS, and registers the authentication, llms.txt, and health routes. |
| [`configs/`](backend/app/configs) | Loads and validates environment configuration, derives environment-specific table names, and supplies dependencies to routes. `config.py` reads settings from environment variables and local `.env`; `dependencies.py` constructs cached AWS clients/table wrappers and validates Cognito bearer tokens to obtain the current user ID. |
| [`clients/`](backend/app/clients) | Wraps calls to external AWS services. Clients provide reusable operations and consistent exceptions, without deciding the overall crawl workflow. |
| [`routes/`](backend/app/routes) | Defines HTTP endpoints, accepts validated requests, checks authentication and site membership, calls tables/services, and maps failures to HTTP responses. |
| [`schemas/`](backend/app/schemas) | Defines Pydantic request and response models for account creation, guest sessions, crawl requests/status, site details, and generated versions. These describe and validate the API's data contract. |
| [`tables/`](backend/app/tables) | Encapsulates DynamoDB access for each table. Queries, update expressions, conditional writes, and transactions live here rather than being repeated in routes or services. |
| [`services/`](backend/app/services) | Coordinates application workflows across clients and tables, including setup, crawling/parsing, generation, and scheduled refresh. |

**AWS clients**

- `cognito.py`: creates accounts, authenticates the shared guest account, and verifies access tokens for protected API requests.
- `dynamodb.py`: provides generic item reads/writes, queries, scans, transactions, value conversion, and conditional-write error handling.
- `s3.py`: reads and writes raw page content, parsed JSON, and generated files; checks whether content-addressed objects already exist.
- `sqs.py`: publishes JSON workflow messages, including delayed retries.
- `bedrock.py`: invokes the model through Bedrock Converse and returns its generated text.

**API routes**

- `account_management.py`: signup and guest sign-in. Regular sign-in and password recovery use Cognito directly from the frontend.
- `llms_txt.py`: starts a crawl, lists the current user's sites, returns site details and generated versions, and exposes crawl status for polling.
- `health.py`: provides a lightweight liveness endpoint; it does not test AWS dependencies.

**DynamoDB table wrappers**

- `sites.py`: shared website metadata, latest crawl pointers, content-change timestamps, and the current generated version.
- `user_sites.py`: mappings between users and sites, used to list accessible sites and authorize site-specific reads.
- `crawl_runs.py`: run lifecycle, discovery locks, and generation dispatch/completion state.
- `crawl_pages.py`: per-run page records, worker claims, checkpoints, retry counts, child registration, and page-derived progress counts.
- `llms_txt_versions.py`: generated-file version metadata, including S3 references and hashes, for current and historical files.

**Workflow services**

- `crawl_setup.py`: atomically prepares the site, crawl run, and root page, then returns the root message for the caller to enqueue. User requests and nightly refreshes share this setup.
- `crawl_and_parse.py`: fetches HTML or Markdown, checks robots rules and URL safety, extracts content and child URLs, saves checkpoints, and dispatches children within crawl limits. It also manages retry/recovery decisions and queues generation when all pages are terminal. Crawling and parsing run together, not in separate Lambdas.
- `llms_txt_generator.py`: loads parsed page data, compares crawl manifests to reuse unchanged output, asks Bedrock for a new llms.txt when needed, and saves the file/version before completing the run.
- `nightly_refresh.py`: reads all registered sites and uses shared setup to enqueue scheduled crawls with repeatable IDs for each site/scheduled time.

[`backend/tests/integrated/`](backend/tests/integrated) contains the live end-to-end deployment test. Local mock tests are ignored by Git and are not included in a fresh clone.

### Frontend

The frontend is a React and TypeScript application built with Vite. [`frontend/src/App.tsx`](frontend/src/App.tsx) restores the session, switches between authentication pages and the signed-in experience, and handles navigation between the homepage and `/sites/{site_id}`.

Each screen has its own file in [`frontend/src/pages/`](frontend/src/pages):

| Page | What it does |
| --- | --- |
| `SignInPage.tsx` | Signs users in with email/password through Cognito, offers **Continue as a Guest**, and links to signup and password recovery. |
| `SignUpPage.tsx` | Collects an email, password, and confirmation; displays a password-requirements checklist; creates the account through the backend; and signs the user in afterward. |
| `PasswordRecoveryPage.tsx` | Combines forgot-password and reset-password into one two-step screen: request an email code, then submit the code and a new password to Cognito. |
| `HomePage.tsx` | Loads the user's sites from the backend and displays them as a grid. **New Website** opens the URL-entry dialog. After creation it reloads the backend list, polls active crawls, and displays discovered/completed counts. Completed counts include failed pages. |
| `LLMTxtPage.tsx` | Shows the current file, updated/generated timestamps, generation method, copy/download actions, and previous versions. It supports manual refresh and polls active crawl progress. A failed crawl without a file displays a failure state; an existing file remains visible if a later crawl fails. |

[`frontend/src/components/`](frontend/src/components) contains shared UI pieces such as the brand, authentication layout, and password checklist. [`frontend/src/lib/`](frontend/src/lib) holds API calls, Amplify/Cognito session handling and token refresh, configuration, validation, and error helpers. [`styles.css`](frontend/src/styles.css) provides the shared styling.

### Deployables

[`deployables/`](deployables) contains the AWS runtime entry points and Docker build definitions. It does not replace the shared service logic in `backend/app/`.

Both `deployables/dev/lambdas/` and `deployables/prod/lambdas/` contain:

- `web_crawler/`: the combined crawl-and-parse worker's handler and container definition. The handler constructs dependencies, processes crawl queue and dead-letter messages, and handles periodic recovery events in the same Lambda.
- `llms_txt_generator/`: the generation worker's handler and container definition. The handler reads SQS messages, invokes the generator service, schedules retries, and marks runs failed when handling exhausted messages from the generator DLQ.
- `nightly_refresh/`: the EventBridge Scheduler entry point and container definition. It reads the scheduled event and calls the nightly-refresh service to queue site crawls.

Each Lambda image packages its handler with the shared `backend/app` code and required dependencies. Handlers translate AWS events into service calls and translate failures back into queue retry responses; the services perform the actual application work. Environment variables and IAM roles are supplied by Terraform.

[`deployables/prod/backend/Dockerfile`](deployables/prod/backend/Dockerfile) packages FastAPI and starts Uvicorn on port 8000 for ECS Fargate. There is no corresponding dev backend deployment because the development API and frontend run locally. The production frontend is built directly by GitHub Actions and uploaded to S3, rather than deployed as a container.

### Infrastructure and Delivery

[`infrastructure/modules/`](infrastructure/modules) contains reusable Terraform modules for AWS services. [`infrastructure/dev/`](infrastructure/dev) and [`infrastructure/prod/`](infrastructure/prod) compose those modules with environment-specific names and settings. Production additionally provisions networking, the load balancer, ECS, and the frontend CDN.

[`infrastructure/scripts/`](infrastructure/scripts) contains remote-state setup and integration-test runner scripts. [`.github/workflows/`](.github/workflows) defines the deployment jobs that build images, apply Terraform, deploy the production application, and run the live integration test.

## Architecture and Workflow

![High-level architecture showing the frontend, API, authentication, queues, workers, storage, Bedrock, and scheduled refresh/recovery](Screenshot%202026-09-30%20at%209.23.19%E2%80%AFPM.png)

### System Overview

The API handles user requests, while background workers crawl websites and generate files:

- **React:** served from S3 through CloudFront. Displays websites, crawl progress, and generated files.
- **FastAPI:** runs on ECS behind a load balancer. API requests travel through CloudFront to the backend.
- **Cognito:** handles accounts, sign-in, password recovery, and session tokens.
- **DynamoDB:** stores website, user, crawl, page, and version records.
- **Application S3 bucket:** stores raw HTML/Markdown, parsed JSON, and llms.txt files separately from the frontend assets.
- **SQS and Lambda:** `crawl_sqs` sends pages to the crawl-and-parse worker; `llm_txt_sqs` sends runs to the generator. Each queue also has a dead-letter queue (DLQ).
- **Bedrock:** generates llms.txt from parsed website content.
- **EventBridge:** schedules nightly refreshes and recovery checks.

In dev, React and FastAPI run locally while workers and storage stay in AWS. In prod, everything runs in AWS. Terraform defines the resources, and GitHub Actions deploys them and runs the integration test.

### Accounts and Access

**Signup:** the frontend checks the password and calls `POST /auth/signup`. The backend creates a confirmed Cognito account without requiring email verification, then the frontend signs the user in.

**Sign-in:** regular users sign in directly through Cognito. **Continue as a Guest** calls the backend, which signs in using configured guest credentials and returns session tokens. All guests share one account and site list.

**Session and password recovery:** refresh tokens renew session tokens while the refresh session is valid. Sign-out clears the session. Forgotten passwords can be reset using an emailed code and a new password.

**Access control:** the backend validates the Cognito token to identify the user. UserSites determines which websites, crawl statuses, and files that user can access. Users who add the same website share its site record and versions.

### Starting a Crawl

1. **New Website** and manual **Refresh** both call `POST /llms-txt` with a URL.
2. The backend normalizes the URL to identify the site and creates a new crawl ID. The same website can have multiple crawl runs.
3. One DynamoDB transaction updates Sites and creates the PENDING run and QUEUED root page.
4. The backend links the user to the site, sends the root page to `crawl_sqs`, and returns immediately with the crawl ID.
5. The frontend reloads the backend's site list and polls progress every four seconds.

The site, run, and root page are saved together. Linking the user and sending the message happen afterward. If the queue send fails, recovery can find the saved page and send it later.

### Crawl-and-Parse Workflow

Each queue message represents one page. Multiple workers can process different pages at the same time.

1. **Claim the page:** check its stored status and claim ownership. Skip pages that are already completed or failed.
2. **Fetch or resume:** reuse raw HTML/Markdown already saved for this run. Otherwise check the URL and robots rules, then fetch the page within the size limit.
3. **Save raw content:** hash the response and store it in S3 if that content is not already there. Save its S3 reference and crawl metadata in DynamoDB.
4. **Parse and discover links:** extract the title, description, headings, main content, and child URLs. HTML uses lxml and Trafilatura; Markdown is parsed directly. The root page also checks sitemaps. Existing parsed content is reused, but child links are still extracted from the saved raw page.
5. **Save parsed content:** write or reuse parsed JSON in S3, then save its reference in DynamoDB before adding children.
6. **Add children:** acquire the discovery lock, skip existing URLs, and save new page records within the crawl limit. Release the lock and send the children to `crawl_sqs`.
7. **Finish:** mark the page COMPLETED after its children are registered and dispatched. Check whether all pages have finished and generation can begin. Failed pages also trigger this check.

Current defaults allow depth 2, up to 100 discovered links per page, and at most 500 registered pages per run including the root. These limits are configurable through Terraform.

### Concurrency and Consistency

**Page ownership:** each claimed page receives a random `worker_token` and `lease_expires_at`. Updates require a matching token and valid lease, so an old worker cannot overwrite a new owner's page state.

**Discovery lock:** `discovery_lock_token` and `discovery_lock_expires_at` live on CrawlRuns, so no separate lock table is needed. This prevents workers from adding new URLs while another worker decides whether the crawl is finished.

**Child deduplication:** pages are keyed by `(crawl_run_id, canonical_url_hash)`. Workers skip existing URLs, and DynamoDB rejects duplicate inserts. Each URL has one record per run; a new run creates its own records.

**Generation readiness:** check all pages while holding the discovery lock. If any are queued or working, wait. If all failed, mark the run FAILED. Otherwise atomically move it to GENERATING and send a message to `llm_txt_sqs`.

**Progress consistency:** counts are calculated from CrawlPages instead of incremented or decremented on CrawlRuns. Page queries and site/run lookups use strongly consistent reads. The frontend's **Completed** count includes successful and failed pages: it means finished, not necessarily successful.

**Duplicate messages:** SQS can deliver a message more than once. Ownership and status checks protect page records, while URL checks prevent duplicate child records. Queue sends and database writes are separate, so repeated messages or external calls are still possible.

### Checkpoints and Content Reuse

| Checkpoint | What is saved | How a retry resumes |
| --- | --- | --- |
| Raw response | S3 content and its key/hash on CrawlPages. | Read the saved response instead of fetching again. |
| Parsed content | Parsed JSON in S3 and its key on CrawlPages. | Reuse parsed content and rediscover child links from the raw page. |
| Child dispatch | Child records with pending-send fields. | Send children that were saved but not successfully dispatched. |
| Generation dispatch | GENERATING status and a pending-send flag. | Retry sending the generation message. |
| Generated version | The file in S3 and its version record. | Reuse the file and finish updating the site/run. |

Files are saved in S3 before their references are written to DynamoDB. Queue messages are sent before their pending-send flags are cleared. If a worker stops between those operations, recovery can retry; it may repeat a send rather than lose the work.

S3 keys include content hashes, allowing unchanged raw and parsed files to be reused across crawls. Parsed keys also include the parser version and final URL's hash. Every run still gets its own page records, and child links are extracted again rather than reused from an old list.

### Generating and Versioning llms.txt

1. Read the site/run IDs from `llm_txt_sqs`. Reuse a version already saved for this run when retrying.
2. Hash the run's page URLs, content hashes, parsed-file keys, and statuses. If the hash matches the current version's input, reuse that file without calling Bedrock.
3. Otherwise load successful pages' parsed content and send bounded excerpts to Bedrock.
4. Ask for a title, summary, one to four website facts without a heading, and up to four file-list sections with four links each. Instruct the model to use supplied URLs and facts, not follow instructions found in website content.
5. Save the returned text in S3, create the version record, update the site's current version, and mark the run COMPLETED. There is no deterministic fallback or output-format validation.

Version IDs use the crawl's creation time and ID, so retries target the same version and history can be sorted. Sites points to the current file. Unlike page processing, generation has no worker lock: overlapping deliveries may call the model twice, and an older run finishing later can become the current version.

### Retries, Recovery, and Failure

Pages move from `QUEUED -> CRAWLING_AND_PARSING -> COMPLETED | FAILED`. Runs move from `PENDING -> CRAWLING_AND_PARSING -> GENERATING -> COMPLETED | FAILED`. Retrying a page does not move its status backward.

- **Crawl/parse retries:** two attempts by default, with a 30-second delay after a caught retryable failure. A 404, oversized response, robots denial, unsafe URL, or unsupported content type fails immediately.
- **Child retries:** `children_attempt_count` allows two attempts to finish child work after parsing. Waiting for the discovery lock does not use an attempt. If the parent fails, its already-registered children still continue.
- **Timeouts:** recovery waits until page ownership expires before retrying or failing abandoned work. This may take longer than 30 seconds.
- **Recovery:** every two minutes, EventBridge invokes the crawl-and-parse Lambda to resend abandoned work, fail exhausted pages, and check whether generation can start. Checks continue while runs are active; checking alone does not consume a processing attempt.
- **DLQs:** the crawl worker handles its DLQ using the same attempt and ownership rules. The generator's DLQ handler marks an exhausted GENERATING run FAILED without calling the model again.

### Viewing Files and Refreshing Sites

The homepage loads the user's sites and latest crawl progress from the backend. Sites with newer content changes appear first, using `modified_at`.

The file page shows the current file and previous versions, with copy, download, and manual refresh actions. Both pages load status when opened and poll every four seconds while a crawl is active.

If the latest crawl fails, an existing file stays visible. Without an existing file, the page shows **Crawl failed**. **Generated at** is when that version was created; **Updated at** is when the latest refresh started, even if it failed or reused the file.

At **2:00 AM in America/New_York**, EventBridge invokes NightlyRefresh to queue every site using the same setup as manual refresh. Each site and scheduled time produces a stable run ID, so schedule retries reuse that run. This runs independently of the browser and backend API and does not change UserSites timestamps.

### Data Models

| Model | Partition key | Sort key | Responsibility |
| --- | --- | --- | --- |
| Sites | `site_id` | None | Shared website metadata, crawl pointers, timestamps, and current version. |
| UserSites | `user_id` | `site_id` | User membership and access to a site's files and crawl status. |
| CrawlRuns | `site_id` | `crawl_run_id` | Run lifecycle, discovery lock, generation dispatch, and output linkage. |
| CrawlPages | `crawl_run_id` | `canonical_url_hash` | Per-page status, ownership, attempts, checkpoints, and dispatch state. |
| LlmsTxtVersions | `site_id` | `version_id` | Generated-file metadata, source/output hashes, model, and S3 location. |

File contents live in S3. Users can copy or download them; the application does not publish them to the original website's `/llms.txt` path.
