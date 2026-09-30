from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.clients.cognito import CognitoTokenVerifier, InvalidCognitoTokenError
from app.configs.config import Settings


class FakeSigningKey:
    def __init__(self, key: Any) -> None:
        self.key = key


class FakeJwksClient:
    def __init__(self, public_key: Any) -> None:
        self.public_key = public_key

    def get_signing_key_from_jwt(self, _: str) -> FakeSigningKey:
        return FakeSigningKey(self.public_key)


def _create_token(
    private_key: Any,
    settings: Settings,
    *,
    token_use: str = "access",
    client_id: str | None = None,
) -> str:
    now = datetime.now(UTC)
    issuer = (
        f"https://cognito-idp.{settings.aws_region}.amazonaws.com/{settings.cognito_user_pool_id}"
    )
    return jwt.encode(
        {
            "sub": "user-123",
            "iss": issuer,
            "client_id": client_id or settings.cognito_app_client_id,
            "token_use": token_use,
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_cognito_token_verifier_returns_sub_from_valid_access_token() -> None:
    settings = Settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = CognitoTokenVerifier(
        settings,
        jwks_client=FakeJwksClient(private_key.public_key()),  # type: ignore[arg-type]
    )

    user_id = verifier.verify_access_token(_create_token(private_key, settings))

    assert user_id == "user-123"


@pytest.mark.parametrize(
    ("token_use", "client_id"),
    [("id", None), ("access", "another-client")],
)
def test_cognito_token_verifier_rejects_wrong_token_type_or_client(
    token_use: str,
    client_id: str | None,
) -> None:
    settings = Settings()
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = CognitoTokenVerifier(
        settings,
        jwks_client=FakeJwksClient(private_key.public_key()),  # type: ignore[arg-type]
    )
    token = _create_token(
        private_key,
        settings,
        token_use=token_use,
        client_id=client_id,
    )

    with pytest.raises(InvalidCognitoTokenError):
        verifier.verify_access_token(token)
