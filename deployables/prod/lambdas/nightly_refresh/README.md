# Nightly refresh Lambda

EventBridge Scheduler invokes this Lambda every day at 3:00 AM in the configured
timezone. It scans the Sites table, creates one deterministic crawl run and root page
per site, and sends each root page to `crawl_sqs`. The existing crawler, parser, and
generator Lambdas handle the rest of the workflow.

The crawl-run ID is derived from the scheduled timestamp and site ID. Scheduler retries
therefore reuse the same run instead of creating duplicate runs.

GitHub Actions builds the image from the repository root:

```bash
docker build --platform linux/amd64 \
  -f deployables/prod/lambdas/nightly_refresh/Dockerfile .
```
