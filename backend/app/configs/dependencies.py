from functools import lru_cache
from typing import Annotated, Any

import boto3
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.clients.cognito import (
    CognitoClient,
    CognitoTokenVerifier,
    InvalidCognitoTokenError,
)
from app.clients.dynamodb import DynamoDBClient
from app.clients.s3 import S3Client
from app.clients.sqs import SQSClient
from app.configs.config import get_settings
from app.tables.crawl_pages import CrawlPagesTable
from app.tables.crawl_runs import CrawlRunsTable
from app.tables.llms_txt_versions import LlmsTxtVersionsTable
from app.tables.sites import SitesTable
from app.tables.user_sites import UserSitesTable

_bearer_scheme = HTTPBearer(auto_error=False)


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
def get_sqs_boto_client() -> Any:
    settings = get_settings()
    return get_boto3_session().client("sqs", region_name=settings.aws_region)


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


@lru_cache
def get_crawl_queue_client() -> SQSClient:
    return SQSClient(
        client=get_sqs_boto_client(),
        queue_url=get_settings().crawl_queue_url,
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

#################################
############ SECURITY ###########
#################################

@lru_cache
def get_cognito_token_verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier(get_settings())


def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
    verifier: Annotated[CognitoTokenVerifier, Depends(get_cognito_token_verifier)],
) -> str:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return verifier.verify_access_token(credentials.credentials)
    except InvalidCognitoTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
