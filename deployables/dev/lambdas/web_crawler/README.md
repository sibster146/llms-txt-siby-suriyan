# Crawl and parse Lambda

The deployment artifact places this `handler.py` at its root and bundles `backend/app` beside it. The handler imports `CrawlAndParseService` from `app.services.crawl_and_parse`, which contains the fetching, parsing, discovery, and workflow logic in one file.

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
    "root_url": "https://example.com/",
    "url": "https://example.com/",
    "canonical_url_hash": "<sha256-of-url>",
    "depth": 0
  }
}
```

Each invocation crawls and parses one page. Unchanged content reuses stored raw
and parsed objects; links are still extracted for child discovery. There is no
separate parser queue. EventBridge also invokes this handler with
`{"action":"recover_crawls"}` to recover interrupted work.

## Environment

- `AWS_REGION`
- `CRAWL_PAGES_TABLE`
- `CRAWL_RUNS_TABLE`
- `APPLICATION_S3_BUCKET`
- `SITES_TABLE`
- `CRAWL_QUEUE_URL`
- `CRAWL_DLQ_URL`
- `CRAWL_DLQ_ARN`
- `LLM_TXT_QUEUE_URL`
- `CRAWLER_USER_AGENT`
- `CRAWLER_REQUEST_TIMEOUT_SECONDS`
- `CRAWLER_MAX_RESPONSE_BYTES`
- `CRAWLER_MAX_ATTEMPTS`
- `CRAWLER_RETRY_DELAY_SECONDS`
- `CRAWLER_LEASE_SECONDS`
- `CRAWLER_MAX_DEPTH`
- `CRAWLER_MAX_LINKS_PER_PAGE`
- `CRAWLER_MAX_DISCOVERED_PAGES`
- `PARSER_VERSION`
