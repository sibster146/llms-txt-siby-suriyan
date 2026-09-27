from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class CreateLlmsTxtRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    url: HttpUrl


class CreateLlmsTxtResponse(BaseModel):
    site_id: str
    crawl_run_id: str
    url: HttpUrl
    status: Literal["PENDING"]
