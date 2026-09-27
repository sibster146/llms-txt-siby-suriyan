from functools import lru_cache
from typing import Any

import boto3

from app.clients.cognito import CognitoClient
from app.clients.dynamodb import DynamoDBClient
from app.clients.s3 import S3Client
from app.configs.config import get_settings
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable


@lru_cache
def get_boto3_session() -> boto3.Session:
    settings = get_settings()
    return boto3.Session(region_name=settings.aws_region)


@lru_cache
def get_dynamodb_resource() -> Any:
    settings = get_settings()
    return get_boto3_session().resource("dynamodb", region_name=settings.aws_region)


@lru_cache
def get_s3_boto_client() -> Any:
    settings = get_settings()
    return get_boto3_session().client("s3", region_name=settings.aws_region)


@lru_cache
def get_cognito_client() -> CognitoClient:
    return CognitoClient(get_settings())


@lru_cache
def get_s3_client() -> S3Client:
    settings = get_settings()
    return S3Client(
        client=get_s3_boto_client(),
        bucket_name=settings.application_s3_bucket,
    )


def _get_dynamodb_client(table_name: str) -> DynamoDBClient:
    return DynamoDBClient(table=get_dynamodb_resource().Table(table_name))


@lru_cache
def get_sites_dynamodb_client() -> DynamoDBClient:
    return _get_dynamodb_client(get_settings().sites_dynamodb_table)


@lru_cache
def get_user_sites_dynamodb_client() -> DynamoDBClient:
    return _get_dynamodb_client(get_settings().user_sites_dynamodb_table)


@lru_cache
def get_crawl_runs_dynamodb_client() -> DynamoDBClient:
    return _get_dynamodb_client(get_settings().crawl_runs_dynamodb_table)


@lru_cache
def get_crawl_pages_dynamodb_client() -> DynamoDBClient:
    return _get_dynamodb_client(get_settings().crawl_pages_dynamodb_table)


@lru_cache
def get_llms_txt_versions_dynamodb_client() -> DynamoDBClient:
    return _get_dynamodb_client(get_settings().llms_txt_versions_dynamodb_table)


@lru_cache
def get_sites_table() -> SitesTable:
    return SitesTable(get_sites_dynamodb_client())


@lru_cache
def get_user_sites_table() -> UserSitesTable:
    return UserSitesTable(get_user_sites_dynamodb_client())


@lru_cache
def get_crawl_runs_table() -> CrawlRunsTable:
    return CrawlRunsTable(get_crawl_runs_dynamodb_client())


@lru_cache
def get_crawl_pages_table() -> CrawlPagesTable:
    return CrawlPagesTable(get_crawl_pages_dynamodb_client())


@lru_cache
def get_llms_txt_versions_table() -> LlmsTxtVersionsTable:
    return LlmsTxtVersionsTable(get_llms_txt_versions_dynamodb_client())
