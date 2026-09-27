from typing import Literal

from pydantic import BaseModel, ConfigDict, HttpUrl


class CreateLlmsTxtRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl


class CreateLlmsTxtResponse(BaseModel):
    site_id: str
    crawl_run_id: str
    url: HttpUrl
    status: Literal["PENDING"]
