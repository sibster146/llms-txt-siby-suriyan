from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    aws_region: str = Field(alias="AWS_REGION", min_length=1)
    environment: Literal["dev", "prod"] = Field(alias="ENVIRONMENT")
    project_name: str = Field(
        alias="PROJECT_NAME",
        pattern=r"^[a-z0-9_]+$",
    )
    application_s3_bucket: str = Field(alias="APPLICATION_S3_BUCKET", min_length=3)
    crawl_queue_url: str = Field(alias="CRAWL_QUEUE_URL", min_length=1)
    cognito_user_pool_id: str = Field(alias="COGNITO_USER_POOL_ID", min_length=1)
    cognito_app_client_id: str = Field(alias="COGNITO_APP_CLIENT_ID", min_length=1)
    cors_origins: str = Field(alias="CORS_ORIGINS", min_length=1)

    @property
    def resource_prefix(self) -> str:
        return f"{self.environment}_{self.project_name}"

    @property
    def sites_dynamodb_table(self) -> str:
        return f"{self.resource_prefix}_sites"

    @property
    def user_sites_dynamodb_table(self) -> str:
        return f"{self.resource_prefix}_user_sites"

    @property
    def crawl_runs_dynamodb_table(self) -> str:
        return f"{self.resource_prefix}_crawl_runs"

    @property
    def crawl_pages_dynamodb_table(self) -> str:
        return f"{self.resource_prefix}_crawl_pages"

    @property
    def llms_txt_versions_dynamodb_table(self) -> str:
        return f"{self.resource_prefix}_llms_txt_versions"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
