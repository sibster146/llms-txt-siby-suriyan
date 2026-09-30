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
    """Validate access tokens issued by the configured Cognito pool and app client."""

    def __init__(self, settings: Settings, jwks_client: PyJWKClient | None = None) -> None:
        """Configure the expected issuer, app client, and signing-key lookup.

        Args:
            settings: AWS region, Cognito user pool ID, and app client ID.
            jwks_client: Optional signing-key client. If omitted, create a
                PyJWKClient pointing to the pool's JWKS endpoint with key caching.

        Signing keys are fetched as needed during token verification, not here.
        """
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
        """Verify a Cognito access JWT and return its user ID from the sub claim.

        Args:
            token: Encoded access token, without the Bearer prefix.

        Returns:
            The nonempty sub claim identifying the authenticated Cognito user.

        Raises:
            InvalidCognitoTokenError: If PyJWT rejects the token or signing-key
                lookup, or its token type, app client, or user ID is invalid.

        Validates the RS256 signature, issuer, expiration, and required claims.
        Audience validation is disabled; client_id is checked against the
        configured app client instead. ID tokens are rejected. This verifies
        the JWT locally using Cognito signing keys, not session revocation.
        """
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
    """Wrap Cognito administrative account creation and password authentication."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        """Configure the target user pool, app client, and Cognito API client.

        Args:
            settings: AWS region, Cognito user pool ID, and app client ID.
            client: Optional boto3-compatible Cognito IDP client. If omitted,
                create one using boto3's default credential resolution.
        """
        self._user_pool_id = settings.cognito_user_pool_id
        self._app_client_id = settings.cognito_app_client_id
        self._client = client or boto3.client("cognito-idp", region_name=settings.aws_region)

    def create_user(self, email: str, password: str) -> str:
        """Create a confirmed user with a permanent password and no invitation.

        Args:
            email: Email used as the username, stripped and lowercased here.
            password: Password to set permanently, subject to the pool's policy.

        Returns:
            The created user's sub attribute, or the normalized email if Cognito
            does not include sub in the creation response.

        Raises:
            UserAlreadyExistsError: If the username or alias already exists.
            InvalidUserPasswordError: If Cognito rejects the password policy.
            CognitoRateLimitError: If Cognito throttles either operation.
            CognitoClientError: For other mapped Cognito API failures.

        Marks email_verified=true administratively without verifying ownership
        by email. If setting the permanent password fails with a ClientError,
        attempts to delete the partially created user before raising the error.
        """
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
        """Authenticate through Cognito's ADMIN_USER_PASSWORD_AUTH flow.

        Args:
            email: Username email, stripped and lowercased before authentication.
            password: User's password, passed unchanged to Cognito.

        Returns:
            Cognito's AuthenticationResult dictionary containing AccessToken.
            Other returned fields, such as refresh/ID tokens and expiry, are
            preserved but are not validated by this method.

        Raises:
            CognitoAuthenticationError: If authentication is rejected or the
                response lacks a token result, including unresolved challenges.
            CognitoRateLimitError: If Cognito throttles the request.
            CognitoClientError: For other mapped Cognito API failures.

        This method does not complete MFA or new-password challenges.
        """
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
        """Best-effort rollback of a newly created user after password setup fails.

        Args:
            email: The already-normalized username used during account creation.

        Suppresses Cognito ClientError failures so they do not replace the
        original password-setting error. Other exception types propagate.
        """
        with suppress(ClientError):
            self._client.admin_delete_user(
                UserPoolId=self._user_pool_id,
                Username=email,
            )

    @staticmethod
    def _raise_client_error(error: ClientError) -> None:
        """Translate a Cognito ClientError into an application exception.

        Args:
            error: Boto3 error whose AWS error code determines the exception type.

        Raises:
            UserAlreadyExistsError: For username or alias conflicts.
            InvalidUserPasswordError: For password-policy violations.
            CognitoRateLimitError: For limit-exceeded or throttling responses.
            CognitoAuthenticationError: For authorization failures, required
                password resets, unconfirmed users, or missing users.
            CognitoClientError: For all other AWS error codes.

        Always raises, preserving the original ClientError as the cause.
        """
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
