# HTML parser Lambda

Consumes `parse_sqs`, extracts same-site links from every page, and stores
structured page content for changed HTML. Unchanged HTML reuses its existing
parsed S3 object while links are extracted again.

Parsed objects use this key format:

```text
parsed/{parser_version}/{site_id}/{canonical_url_hash}/{raw_html_hash}.json
```
