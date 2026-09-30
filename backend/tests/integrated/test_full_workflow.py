"""Live guest -> HTTP API -> AWS workers -> generated file, followed by scoped cleanup."""

import os
import time
from hashlib import sha256
from uuid import uuid4

import boto3
import jwt
import pytest
from boto3.dynamodb.conditions import Attr, Key

URL = "https://www.roblox.com/"
SITE_ID = f"site_{sha256(URL.encode()).hexdigest()}"
TERMINAL = {"COMPLETED", "FAILED"}


def read_all(table, operation, **kwargs):
    items = []
    while True:
        result = getattr(table, operation)(ConsistentRead=True, **kwargs)
        items.extend(result.get("Items", []))
        if not result.get("LastEvaluatedKey"):
            return items
        kwargs["ExclusiveStartKey"] = result["LastEvaluatedKey"]


class CrawlTestData:
    def __init__(self):
        self.owner = str(uuid4())
        self.user_id = None
        self.run_id = None
        session = boto3.Session(
            profile_name=os.environ.get("AWS_PROFILE_NAME") or None,
            region_name=os.environ["AWS_REGION"],
        )
        environment = os.environ["ENVIRONMENT"]
        assert environment in {"dev", "prod"}
        prefix = f"{environment}_{os.environ['PROJECT_NAME']}"
        dynamodb = session.resource("dynamodb")
        self.tables = {
            name: dynamodb.Table(f"{prefix}_{name}")
            for name in ("sites", "user_sites", "crawl_runs", "crawl_pages", "llms_txt_versions")
        }
        self.s3 = session.client("s3")
        self.bucket = os.environ["APPLICATION_S3_BUCKET"]
        account = session.client("sts").get_caller_identity()["Account"]
        assert self.bucket == f"{prefix.replace('_', '-')}-s3-{account}", (
            "Bucket must match the selected environment, project, and AWS account"
        )
        lambdas = session.client("lambda")
        # Bound the lifetime of any worker that already read the run before cancellation.
        self.quiet_seconds = 10 + max(
            lambdas.get_function_configuration(FunctionName=f"{prefix}_{name}")["Timeout"]
            for name in ("web_crawler", "generator", "nightly_refresh")
        )

    def rows(self, name):
        return read_all(
            self.tables[name], "query", KeyConditionExpression=Key("site_id").eq(SITE_ID)
        )

    def mappings(self):
        return read_all(
            self.tables["user_sites"], "scan", FilterExpression=Attr("site_id").eq(SITE_ID)
        )

    def objects(self):
        # Include historical object versions and delete markers, not just visible files.
        for prefix in (f"raw/{SITE_ID}/", f"llms-txt/{SITE_ID}/", "parsed/"):
            for page in self.s3.get_paginator("list_object_versions").paginate(
                Bucket=self.bucket, Prefix=prefix
            ):
                for item in page.get("Versions", []) + page.get("DeleteMarkers", []):
                    if SITE_ID in item["Key"].split("/"):
                        yield {"Key": item["Key"], "VersionId": item["VersionId"]}

    def reserve(self):
        assert not self.rows("crawl_runs"), "Roblox already has runs; refusing to overwrite them"
        assert not self.rows("llms_txt_versions"), "Roblox already has generated versions"
        assert not self.mappings(), "Roblox is already associated with a user"
        assert not next(self.objects(), None), "Roblox already has stored files"
        self.tables["sites"].put_item(
            Item={"site_id": SITE_ID, "integration_test_owner": self.owner},
            ConditionExpression=Attr("site_id").not_exists(),
        )

    def cleanup(self):
        site = (
            self.tables["sites"]
            .get_item(Key={"site_id": SITE_ID}, ConsistentRead=True)
            .get("Item", {})
        )
        assert site.get("integration_test_owner") == self.owner, "Test site ownership changed"
        runs = self.rows("crawl_runs")
        assert all(r["crawl_run_id"] == self.run_id for r in runs), (
            "Unconfirmed or additional crawl appeared; preserving data for inspection"
        )
        mappings = self.mappings()
        assert all(m["user_id"] == self.user_id for m in mappings), "Another user owns this site"
        for run in runs:
            if run["status"] not in TERMINAL:
                self.tables["crawl_runs"].update_item(
                    Key={"site_id": SITE_ID, "crawl_run_id": run["crawl_run_id"]},
                    UpdateExpression=(
                        "SET #s = :failed REMOVE discovery_lock_token, "
                        "discovery_lock_expires_at, generation_dispatch_pending"
                    ),
                    ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":failed": "FAILED"},
                    ConditionExpression=Attr("crawl_run_id").exists(),
                )
        if runs:
            print(f"Waiting {self.quiet_seconds}s for in-flight workers before cleanup", flush=True)
            time.sleep(self.quiet_seconds)
        assert {r["crawl_run_id"] for r in self.rows("crawl_runs")} == {
            r["crawl_run_id"] for r in runs
        }, "Another crawl started during cleanup; retaining data"
        assert sorted(self.mappings(), key=lambda m: m["user_id"]) == sorted(
            mappings, key=lambda m: m["user_id"]
        ), "Site membership changed during cleanup"

        for item in list(self.objects()):
            self.s3.delete_object(Bucket=self.bucket, **item)
        for version in self.rows("llms_txt_versions"):
            self.tables["llms_txt_versions"].delete_item(
                Key={"site_id": SITE_ID, "version_id": version["version_id"]}
            )
        for run in runs:
            pages = read_all(
                self.tables["crawl_pages"],
                "query",
                KeyConditionExpression=Key("crawl_run_id").eq(run["crawl_run_id"]),
            )
            with self.tables["crawl_pages"].batch_writer() as batch:
                for page in pages:
                    batch.delete_item(
                        Key={
                            "crawl_run_id": run["crawl_run_id"],
                            "canonical_url_hash": page["canonical_url_hash"],
                        }
                    )
            assert not read_all(
                self.tables["crawl_pages"],
                "query",
                KeyConditionExpression=Key("crawl_run_id").eq(run["crawl_run_id"]),
            ), "Page cleanup incomplete"
            self.tables["crawl_runs"].delete_item(
                Key={"site_id": SITE_ID, "crawl_run_id": run["crawl_run_id"]}
            )
        for mapping in mappings:
            self.tables["user_sites"].delete_item(
                Key={"user_id": mapping["user_id"], "site_id": SITE_ID}
            )
        self.tables["sites"].delete_item(
            Key={"site_id": SITE_ID},
            ConditionExpression=Attr("integration_test_owner").eq(self.owner),
        )
        assert not next(self.objects(), None), "S3 cleanup incomplete"
        assert not self.rows("crawl_runs") and not self.rows("llms_txt_versions")
        assert not self.mappings()
        assert "Item" not in self.tables["sites"].get_item(
            Key={"site_id": SITE_ID}, ConsistentRead=True
        )
        print(f"Cleaned test site {SITE_ID}", flush=True)


@pytest.fixture
def crawl_data(live_api):
    user_id = guest_login(live_api)
    data = CrawlTestData()
    data.user_id = user_id
    data.reserve()
    try:
        yield data
    finally:
        data.cleanup()


def guest_login(client):
    login = client.post("/auth/guest")
    assert login.status_code == 200, f"Guest login failed: HTTP {login.status_code}"
    session = login.json()
    # Check environment routing before a destructive test; the API validates the JWT itself.
    claims = jwt.decode(session["access_token"], options={"verify_signature": False})
    issuer = (
        f"https://cognito-idp.{os.environ['AWS_REGION']}.amazonaws.com/"
        f"{os.environ['COGNITO_USER_POOL_ID']}"
    )
    assert claims["iss"] == issuer, "API is using a different environment's Cognito pool"
    assert claims["client_id"] == os.environ["COGNITO_APP_CLIENT_ID"]
    client.headers["Authorization"] = f"Bearer {session['access_token']}"
    return session["user_id"]


def authenticated_get(client, path):
    response = client.get(path)
    if response.status_code == 401:
        guest_login(client)
        response = client.get(path)
    return response


def test_guest_can_generate_llms_txt_for_roblox(live_api, crawl_data):
    response = live_api.post("/llms-txt", json={"url": URL})
    assert response.status_code == 201, f"POST /llms-txt: {response.status_code} {response.text}"
    request = response.json()
    assert request["site_id"] == SITE_ID
    run_id = request["crawl_run_id"]
    crawl_data.run_id = run_id
    print(f"Integration crawl: {run_id}", flush=True)
    deadline = time.monotonic() + int(os.environ.get("INTEGRATION_TIMEOUT_SECONDS", "1200"))
    previous = None
    while time.monotonic() < deadline:
        response = authenticated_get(live_api, f"/llms-txt/{SITE_ID}/crawls/{run_id}")
        assert response.status_code == 200, f"Status lookup failed: {response.status_code}"
        result = response.json()
        if result != previous:
            print(result, flush=True)
            previous = result
        if result["status"] in TERMINAL:
            break
        time.sleep(4)
    else:
        pytest.fail(f"Crawl {run_id} timed out; last status: {previous}")

    run = crawl_data.tables["crawl_runs"].get_item(
        Key={"site_id": SITE_ID, "crawl_run_id": run_id}, ConsistentRead=True
    )["Item"]
    assert result["status"] == "COMPLETED", f"Crawl failed: {run}"
    assert result["pending_page_count"] == 0
    assert result["completed_page_count"] > 0
    assert result["discovered_page_count"] == (
        result["completed_page_count"] + result["failed_page_count"]
    )
    version_id = run["llms_txt_version_id"]
    response = authenticated_get(live_api, f"/llms-txt/sites/{SITE_ID}/versions/{version_id}")
    assert response.status_code == 200
    version = response.json()
    assert version["crawl_run_id"] == run_id
    assert version["content"].strip(), "Generated file is empty"
    assert sha256(version["content"].encode()).hexdigest() == version["content_hash"]
    print(f"Verified generated version {version_id}", flush=True)
