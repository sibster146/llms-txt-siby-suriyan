# llms.txt generator Lambda

This image contains the thin SQS handler plus the shared backend application code.
The Lambda consumes `llm_txt_sqs`, loads parsed pages for the crawl run, asks Amazon
Bedrock's Moonshot AI Kimi K3 model for the complete `llms.txt`, and stores the model
response unchanged. Output validation and deterministic fallback remain disabled; model
or API failures follow the normal queue retry path.

Before calling Bedrock, the generator hashes a sorted manifest of the crawl's page URLs,
parse statuses, raw-content hashes, and parsed S3 keys. If that hash matches the site's
current version, the crawl reuses that version without invoking Bedrock or writing a new
S3 object or DynamoDB version record.

Unexpected processing failures are requeued with a 30-second delivery delay. The
message carries its attempt number and is sent to `llm_txt_dlq` after four failed
attempts. If scheduling the retry fails, the original message remains unacknowledged.

The same Lambda consumes `llm_txt_dlq` through a separate event-source mapping
(concurrency 2), identified by `LLM_TXT_DLQ_ARN`. It does not call Bedrock for DLQ
messages: it conditionally changes a GENERATING crawl run to FAILED, stores a bounded
`error_message`, updates `updated_at`, and removes pending-generation dispatch state.
Completed, already-failed, and deleted runs are left unchanged.

This also handles messages moved to the DLQ by SQS after timeouts or exhausted
deliveries. If the database write fails, the message stays on the DLQ for retry.
Malformed messages without identifiable run IDs remain on the DLQ and are logged
for manual investigation; the DLQ retains messages for up to 14 days.

Generated files are stored as immutable versions at:

```text
llms-txt/{site_id}/{version_id}/llms.txt
```

GitHub Actions builds the image from the repository root:

```bash
docker build --platform linux/amd64 \
  -f deployables/prod/lambdas/llms_txt_generator/Dockerfile .
```
