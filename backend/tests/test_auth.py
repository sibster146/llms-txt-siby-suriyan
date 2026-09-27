from fastapi.testclient import TestClient

from app.configs.dependencies import get_cognito_client
from app.main import app


class FakeCognitoClient:
    def __init__(self) -> None:
        self.created_user: tuple[str, str] | None = None

    def create_user(self, email: str, password: str) -> str:
        self.created_user = (email, password)
        return "user-123"


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
