from contextlib import suppress
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.configs.config import Settings


class CognitoClientError(Exception):
    """Base exception for Cognito client failures."""


class UserAlreadyExistsError(CognitoClientError):
    """Raised when a Cognito user already exists."""


class InvalidUserPasswordError(CognitoClientError):
    """Raised when a password does not match the user-pool policy."""


class CognitoRateLimitError(CognitoClientError):
    """Raised when Cognito throttles a request."""


class CognitoClient:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._user_pool_id = settings.cognito_user_pool_id
        self._client = client or boto3.client("cognito-idp", region_name=settings.aws_region)

    def create_user(self, email: str, password: str) -> str:
        normalized_email = email.strip().lower()

        try:
            response = self._client.admin_create_user(
                UserPoolId=self._user_pool_id,
                Username=normalized_email,
                TemporaryPassword=password,
                MessageAction="SUPPRESS",
                UserAttributes=[
                    {"Name": "email", "Value": normalized_email},
                    {"Name": "email_verified", "Value": "true"},
                ],
            )

            try:
                self._client.admin_set_user_password(
                    UserPoolId=self._user_pool_id,
                    Username=normalized_email,
                    Password=password,
                    Permanent=True,
                )
            except ClientError:
                self._delete_partial_user(normalized_email)
                raise
        except ClientError as error:
            self._raise_client_error(error)

        attributes = response.get("User", {}).get("Attributes", [])
        user_id = next(
            (attribute["Value"] for attribute in attributes if attribute["Name"] == "sub"),
            normalized_email,
        )
        return user_id

    def _delete_partial_user(self, email: str) -> None:
        with suppress(ClientError):
            self._client.admin_delete_user(
                UserPoolId=self._user_pool_id,
                Username=email,
            )

    @staticmethod
    def _raise_client_error(error: ClientError) -> None:
        error_code = error.response.get("Error", {}).get("Code")

        if error_code in {"UsernameExistsException", "AliasExistsException"}:
            raise UserAlreadyExistsError from error

        if error_code == "InvalidPasswordException":
            raise InvalidUserPasswordError from error

        if error_code in {"LimitExceededException", "TooManyRequestsException"}:
            raise CognitoRateLimitError from error

        raise CognitoClientError from error
