# Web crawler Lambda

The deployment artifact places this `handler.py` at its root and copies the repository's `backend` directory beside it. The handler imports the reusable clients, table abstractions, and crawler service from that bundled directory.

GitHub Actions builds the image from the repository root:

```bash
docker build --platform linux/amd64 -f deployables/dev/lambdas/web_crawler/Dockerfile .
```

Each image is tagged with its Git commit SHA and pushed to the environment's ECR repository before Terraform updates the Lambda.

## SQS message

```json
{
  "action": "crawl_url",
  "payload": {
    "site_id": "site_...",
    "crawl_run_id": "crawl_...",
    "url": "https://example.com/",
    "canonical_url_hash": "<sha256-of-url>",
    "depth": 0
  }
}
```

## Environment

- `AWS_REGION`
- `CRAWL_PAGES_TABLE`
- `CRAWL_RUNS_TABLE`
- `APPLICATION_S3_BUCKET`
- `PARSE_QUEUE_URL`
- `CRAWLER_USER_AGENT`
- `CRAWLER_REQUEST_TIMEOUT_SECONDS`
- `CRAWLER_MAX_RESPONSE_BYTES`
- `CRAWLER_MAX_ATTEMPTS`
