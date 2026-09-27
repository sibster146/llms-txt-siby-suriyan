# llms-txt-siby-suriyan

Web application for generating and maintaining `llms.txt` files. The current slice provides a custom React authentication experience backed by FastAPI and Amazon Cognito.

## Project structure

- `frontend`: React, TypeScript, Vite, and AWS Amplify Auth
- `backend`: FastAPI and the AWS SDK for Python
- `infrastructure`: reusable Terraform modules and environment configurations

## Provision Cognito

Development infrastructure is provisioned only by GitHub Actions. Commit and push to a `feature/**` branch or `dev`:

```bash
git push origin feature/setup
```

The `Deploy Dev` workflow creates the remote state bucket, applies Terraform, and publishes the Cognito IDs in its job summary. See `infrastructure/README.md` for the required GitHub environment variables and IAM policy.

## Run the backend

Create `backend/.env` from `backend/.env.example`. Set `COGNITO_USER_POOL_ID` from
`cognito_user_pool_id`, `COGNITO_APP_CLIENT_ID` from `cognito_web_client_id`, and
`CRAWL_QUEUE_URL` from the `crawl` value in `sqs_queue_urls`. For local development,
set `AWS_PROFILE_NAME` to the AWS CLI profile that can access the development resources.

```bash
source venv/bin/activate
uvicorn app.main:app --reload --app-dir backend
```

The API runs at `http://localhost:8000`; interactive API documentation is available at `http://localhost:8000/docs`.

## Run the frontend

Create `frontend/.env` from `frontend/.env.example`, then set:

- `VITE_COGNITO_USER_POOL_ID` from `cognito_user_pool_id`
- `VITE_COGNITO_USER_POOL_CLIENT_ID` from `cognito_web_client_id`
- `VITE_API_URL=http://localhost:8000`

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Checks

```bash
venv/bin/ruff check backend
venv/bin/pytest backend
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run build
terraform -chdir=infrastructure/dev validate
```

## Authentication flow

1. React submits account creation to `POST /auth/signup`.
2. FastAPI creates a confirmed Cognito user, suppresses Cognito's invitation email, marks the email as verified, and sets a permanent password.
3. React signs in directly with Cognito using SRP. Login passwords do not pass through FastAPI.
4. The custom forgot-password screens call Cognito to send and confirm reset codes.

The signup endpoint is intentionally minimal for this first slice. Add abuse protection before opening it to public traffic.
