import jwt
from fastapi.testclient import TestClient

from app.configs.dependencies import get_cognito_client
from app.main import app


class FakeCognitoClient:
    def __init__(self) -> None:
        self.created_user: tuple[str, str] | None = None

    def create_user(self, email: str, password: str) -> str:
        self.created_user = (email, password)
        return "user-123"

    def authenticate_user(self, email: str, password: str) -> dict[str, object]:
        return {
            "AccessToken": jwt.encode(
                {"sub": "guest-123"},
                "test-secret-that-is-at-least-32-bytes",
                algorithm="HS256",
            ),
            "IdToken": jwt.encode(
                {
                    "sub": "guest-123",
                    "cognito:username": "guest@example.com",
                },
                "test-secret-that-is-at-least-32-bytes",
                algorithm="HS256",
            ),
            "RefreshToken": "guest-refresh-token",
            "ExpiresIn": 3600,
        }


def test_signup_creates_a_confirmed_user() -> None:
    cognito_client = FakeCognitoClient()
    app.dependency_overrides[get_cognito_client] = lambda: cognito_client

    with TestClient(app) as test_client:
        response = test_client.post(
            "/auth/signup",
            json={"email": "Person@Example.com", "password": "StrongPassword1!"},
        )

    app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json() == {"user_id": "user-123", "email": "person@example.com"}
    assert cognito_client.created_user == ("person@example.com", "StrongPassword1!")


def test_signup_rejects_an_invalid_email() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/auth/signup",
            json={"email": "not-an-email", "password": "StrongPassword1!"},
        )

    assert response.status_code == 422


def test_guest_signin_returns_cognito_session_without_exposing_password() -> None:
    cognito_client = FakeCognitoClient()
    app.dependency_overrides[get_cognito_client] = lambda: cognito_client

    with TestClient(app) as test_client:
        response = test_client.post("/auth/guest")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "user_id": "guest-123",
        "email": "guest@example.com",
        "access_token": response.json()["access_token"],
        "id_token": response.json()["id_token"],
        "refresh_token": "guest-refresh-token",
        "expires_in": 3600,
    }
    assert "password" not in response.json()
