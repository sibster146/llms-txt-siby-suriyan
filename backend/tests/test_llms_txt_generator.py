import json
from typing import Any

import pytest

from app.clients.bedrock import BedrockClientError
from app.services.llms_txt_generator import (
    GenerationMessageError,
    InvalidGenerationPlanError,
    LlmsTxtGeneratorService,
    PageCandidate,
    _deterministic_plan,
    validate_llms_txt,
)


class FakeSitesTable:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.record = {"site_id": "site-1", "root_url": "https://example.com/"}
        self.completed: list[dict[str, Any]] = []

    def get(self, site_id: str) -> dict[str, Any] | None:
        return self.record if site_id == "site-1" else None

    def mark_generation_completed(self, **kwargs: Any) -> None:
        self.events.append("site")
        self.completed.append(kwargs)


class FakeCrawlRunsTable:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.record = {
            "site_id": "site-1",
            "crawl_run_id": "crawl-1",
            "status": "GENERATING",
            "created_at": "2026-09-28T12:34:56+00:00",
        }
        self.completed: list[dict[str, Any]] = []

    def get(self, **_: Any) -> dict[str, Any]:
        return self.record

    def mark_generation_completed(self, **kwargs: Any) -> None:
        self.events.append("run")
        self.record["status"] = "COMPLETED"
        self.completed.append(kwargs)


class FakeCrawlPagesTable:
    def list_for_run(self, crawl_run_id: str) -> list[dict[str, Any]]:
        assert crawl_run_id == "crawl-1"
        return [
            {
                "status": "PARSED",
                "url": "https://example.com/",
                "depth": 0,
                "parsed_content_s3_key": "parsed/root.json",
            },
            {
                "status": "PARSED",
                "url": "https://example.com/docs/start",
                "depth": 1,
                "parsed_content_s3_key": "parsed/docs.json",
            },
            {
                "status": "FAILED",
                "url": "https://example.com/broken",
                "depth": 1,
            },
        ]


class FakeVersionsTable:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.records: dict[tuple[str, str], dict[str, Any]] = {}

    def get(self, *, site_id: str, version_id: str) -> dict[str, Any] | None:
        return self.records.get((site_id, version_id))

    def create(self, **kwargs: Any) -> None:
        self.events.append("version")
        self.records[(kwargs["site_id"], kwargs["version_id"])] = {
            **kwargs,
            "llms_txt_s3_key": kwargs["s3_key"],
        }


class FakeS3Client:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.objects: dict[str, str] = {
            "parsed/root.json": json.dumps(
                {
                    "url": "https://example.com/",
                    "title": "Example",
                    "description": "Example helps teams build useful things.",
                    "headings": [{"level": "h1", "text": "Welcome"}],
                    "main_content": "Welcome to Example.",
                }
            ),
            "parsed/docs.json": json.dumps(
                {
                    "url": "https://example.com/docs/start",
                    "title": "Getting started",
                    "description": "Set up Example.",
                    "headings": [{"level": "h1", "text": "Getting started"}],
                    "main_content": "Install and configure Example.",
                }
            ),
        }

    def get_text(self, key: str) -> str:
        return self.objects[key]

    def put_text(self, *, key: str, content: str, **_: Any) -> str:
        self.events.append("s3")
        self.objects[key] = content
        return key


class FakeBedrockClient:
    model_id = "amazon.nova-pro-v1:0"

    def __init__(self, result: dict[str, Any] | None = None, *, fail: bool = False) -> None:
        self.result = result or {}
        self.fail = fail
        self.calls = 0

    def generate_json(self, **_: Any) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise BedrockClientError("unavailable")
        return self.result


def _message() -> dict[str, Any]:
    return {
        "action": "generate_llms_txt",
        "payload": {"site_id": "site-1", "crawl_run_id": "crawl-1"},
    }


def _valid_plan() -> dict[str, Any]:
    return {
        "site_name": "Example",
        "summary": "Example helps teams build useful things.",
        "details": ["Use the documentation to get started."],
        "sections": [
            {
                "name": "Documentation",
                "entries": [
                    {
                        "page_id": "page_0002",
                        "title": "Getting started",
                        "description": "Set up Example.",
                    }
                ],
            },
            {
                "name": "Resources",
                "entries": [
                    {
                        "page_id": "page_0001",
                        "title": "Example home",
                        "description": "Overview of Example.",
                    }
                ],
            },
        ],
    }


def _service(
    bedrock: FakeBedrockClient,
) -> tuple[
    LlmsTxtGeneratorService,
    FakeSitesTable,
    FakeCrawlRunsTable,
    FakeVersionsTable,
    FakeS3Client,
    list[str],
]:
    events: list[str] = []
    sites = FakeSitesTable(events)
    runs = FakeCrawlRunsTable(events)
    versions = FakeVersionsTable(events)
    s3 = FakeS3Client(events)
    service = LlmsTxtGeneratorService(
        sites=sites,
        crawl_pages=FakeCrawlPagesTable(),
        crawl_runs=runs,
        versions=versions,
        s3=s3,
        bedrock=bedrock,
    )
    return service, sites, runs, versions, s3, events


def test_generator_uses_nova_plan_and_persists_before_completing() -> None:
    bedrock = FakeBedrockClient(_valid_plan())
    service, sites, runs, versions, s3, events = _service(bedrock)

    result = service.process_message(_message())

    assert result.generation_method == "AMAZON_NOVA_PRO"
    assert result.content.startswith("# Example\n\n> Example helps teams")
    assert "## Documentation" in result.content
    assert "[Getting started](<https://example.com/docs/start>)" in result.content
    assert events == ["s3", "version", "site", "run"]
    assert result.s3_key in s3.objects
    assert versions.records[("site-1", result.version_id)]["model_id"] == ("amazon.nova-pro-v1:0")
    assert sites.completed[0]["version_id"] == result.version_id
    assert runs.completed[0]["version_id"] == result.version_id


def test_generator_falls_back_when_nova_references_an_unknown_page() -> None:
    plan = _valid_plan()
    plan["sections"][0]["entries"][0]["page_id"] = "page_9999"
    service, _, _, _, _, _ = _service(FakeBedrockClient(plan))

    result = service.process_message(_message())

    assert result.generation_method == "DETERMINISTIC_FALLBACK"
    assert "https://example.com/docs/start" in result.content
    assert "page_9999" not in result.content


def test_generator_falls_back_when_bedrock_is_unavailable(caplog: Any) -> None:
    service, _, _, versions, _, _ = _service(FakeBedrockClient(fail=True))

    result = service.process_message(_message())

    assert result.generation_method == "DETERMINISTIC_FALLBACK"
    record = versions.records[("site-1", result.version_id)]
    assert record["model_id"] is None
    assert "error_type=BedrockClientError error=unavailable" in caplog.text


def test_deterministic_fallback_applies_editorial_constraints() -> None:
    pages = [
        PageCandidate(
            page_id="page_root",
            url="https://example.com/",
            title="Example " * 30,
            description="First summary sentence. Second summary sentence. Third is excluded.",
            headings=(),
            excerpt="",
            depth=0,
        ),
        PageCandidate(
            page_id="page_login",
            url="https://example.com/login",
            title="Login",
            description="Sign in to an account.",
            headings=(),
            excerpt="",
            depth=1,
        ),
        *[
            PageCandidate(
                page_id=f"page_{index}",
                url=f"https://example.com/docs/page-{index}",
                title=f"Documentation page {index} " + ("title " * 30),
                description="One useful sentence. A second sentence should not be included.",
                headings=(),
                excerpt="",
                depth=1,
            )
            for index in range(60)
        ],
    ]

    plan = _deterministic_plan("https://example.com/", pages, max_output_links=50)
    entries = [entry for section in plan.sections for entry in section.entries]

    assert len(plan.site_name) <= 80
    assert "Third is excluded" not in plan.summary
    assert len(plan.summary) <= 320
    assert len(plan.sections) <= 8
    assert len(entries) == 50
    assert all(entry.page_id != "page_login" for entry in entries)
    assert all(len(entry.title) <= 100 for entry in entries)
    assert all(len(entry.description) <= 200 for entry in entries)
    assert all("second sentence" not in entry.description.lower() for entry in entries)


def test_generator_retry_reuses_the_existing_version() -> None:
    bedrock = FakeBedrockClient(_valid_plan())
    service, _, runs, _, _, events = _service(bedrock)
    first = service.process_message(_message())
    events.clear()

    second = service.process_message(_message())

    assert second.content == first.content
    assert second.version_id == first.version_id
    assert bedrock.calls == 1
    assert events == ["site", "run"]
    assert runs.record["status"] == "COMPLETED"


def test_generator_rejects_an_invalid_queue_message() -> None:
    service, _, _, _, _, _ = _service(FakeBedrockClient(_valid_plan()))

    with pytest.raises(GenerationMessageError):
        service.process_message({"action": "wrong", "payload": {}})


def test_llms_txt_validator_rejects_unknown_urls_and_bad_sections() -> None:
    with pytest.raises(InvalidGenerationPlanError):
        validate_llms_txt(
            "# Example\n\n> Summary\n\n## Docs\n\n- [Made up](<https://other.example/>)\n",
            {"https://example.com/"},
        )

    with pytest.raises(InvalidGenerationPlanError):
        validate_llms_txt(
            "# Example\n\n> Summary\n\n## Empty\n",
            {"https://example.com/"},
        )
