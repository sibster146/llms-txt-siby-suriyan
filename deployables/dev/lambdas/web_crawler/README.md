# Web crawler Lambda

The deployment artifact places this `handler.py` at its root and copies the repository's `backend` directory beside it. The handler imports the reusable clients, table abstractions, and crawler service from that bundled directory.

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
- `APPLICATION_S3_BUCKET`
- `PARSE_QUEUE_URL`
- `CRAWLER_USER_AGENT`
- `CRAWLER_REQUEST_TIMEOUT_SECONDS`
- `CRAWLER_MAX_RESPONSE_BYTES`
- `CRAWLER_MAX_ATTEMPTS`
