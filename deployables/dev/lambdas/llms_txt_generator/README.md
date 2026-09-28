# llms.txt generator Lambda

This image contains the thin SQS handler plus the shared backend application code.
The Lambda consumes `llm_txt_sqs`, loads parsed pages for the crawl run, asks Amazon
Nova Pro for a structured plan, validates and renders the plan, and falls back to
deterministic generation if the model response is unavailable or invalid.

Unexpected processing failures are requeued with a 30-second delivery delay. The
message carries its attempt number and is sent to `llm_txt_dlq` after four failed
attempts. If scheduling the retry fails, the original message remains unacknowledged.

Generated files are stored as immutable versions at:

```text
llms-txt/{site_id}/{version_id}/llms.txt
```

GitHub Actions builds the image from the repository root:

```bash
docker build --platform linux/amd64 \
  -f deployables/dev/lambdas/llms_txt_generator/Dockerfile .
```
