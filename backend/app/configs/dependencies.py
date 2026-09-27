from functools import lru_cache

from app.clients.cognito import CognitoClient
from app.configs.config import get_settings


@lru_cache
def get_cognito_client() -> CognitoClient:
    return CognitoClient(get_settings())
