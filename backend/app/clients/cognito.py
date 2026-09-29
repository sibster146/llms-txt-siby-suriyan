from contextlib import suppress
from typing import Any

import boto3
import jwt
from botocore.exceptions import ClientError
from jwt import PyJWKClient
from jwt.exceptions import PyJWTError

from app.configs.config import Settings


class CognitoClientError(Exception):
    """Base exception for Cognito client failures."""


class UserAlreadyExistsError(CognitoClientError):
    """Raised when a Cognito user already exists."""


class InvalidUserPasswordError(CognitoClientError):
    """Raised when a password does not match the user-pool policy."""


class CognitoRateLimitError(CognitoClientError):
    """Raised when Cognito throttles a request."""


class InvalidCognitoTokenError(CognitoClientError):
    """Raised when a Cognito access token cannot be trusted."""


class CognitoAuthenticationError(CognitoClientError):
    """Raised when Cognito rejects an authentication request."""


class CognitoTokenVerifier:
    def __init__(self, settings: Settings, jwks_client: PyJWKClient | None = None) -> None:
        self._app_client_id = settings.cognito_app_client_id
        self._issuer = (
            f"https://cognito-idp.{settings.aws_region}.amazonaws.com/"
            f"{settings.cognito_user_pool_id}"
        )
        self._jwks_client = jwks_client or PyJWKClient(
            f"{self._issuer}/.well-known/jwks.json",
            cache_keys=True,
        )

    def verify_access_token(self, token: str) -> str:
        try:
            signing_key = self._jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                options={
                    "verify_aud": False,
                    "require": ["exp", "iat", "iss", "sub", "token_use", "client_id"],
                },
            )
        except PyJWTError as error:
            raise InvalidCognitoTokenError from error

        if claims["token_use"] != "access":
            raise InvalidCognitoTokenError
        if claims["client_id"] != self._app_client_id:
            raise InvalidCognitoTokenError

        user_id = claims["sub"]
        if not isinstance(user_id, str) or not user_id:
            raise InvalidCognitoTokenError
        return user_id


class CognitoClient:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._user_pool_id = settings.cognito_user_pool_id
        self._app_client_id = settings.cognito_app_client_id
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

    def authenticate_user(self, email: str, password: str) -> dict[str, Any]:
        try:
            response = self._client.admin_initiate_auth(
                UserPoolId=self._user_pool_id,
                ClientId=self._app_client_id,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={
                    "USERNAME": email.strip().lower(),
                    "PASSWORD": password,
                },
            )
        except ClientError as error:
            self._raise_client_error(error)

        result = response.get("AuthenticationResult")
        if not isinstance(result, dict) or "AccessToken" not in result:
            raise CognitoAuthenticationError
        return result

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

        if error_code in {
            "NotAuthorizedException",
            "PasswordResetRequiredException",
            "UserNotConfirmedException",
            "UserNotFoundException",
        }:
            raise CognitoAuthenticationError from error

        raise CognitoClientError from error
