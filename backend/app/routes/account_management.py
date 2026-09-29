from typing import Annotated, Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from jwt.exceptions import PyJWTError

from app.clients.cognito import (
    CognitoAuthenticationError,
    CognitoClient,
    CognitoClientError,
    CognitoRateLimitError,
    InvalidUserPasswordError,
    UserAlreadyExistsError,
)
from app.configs.config import Settings, get_settings
from app.configs.dependencies import get_cognito_client
from app.schemas.account_management import (
    GuestSessionResponse,
    SignUpRequest,
    UserResponse,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def _authentication_result(result: dict[str, Any]) -> tuple[str, int]:
    access_token = result.get("AccessToken")
    expires_in = result.get("ExpiresIn")
    if not isinstance(access_token, str) or not isinstance(expires_in, int):
        raise CognitoAuthenticationError
    return access_token, expires_in


def _guest_authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Guest access is temporarily unavailable.",
    )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def sign_up(
    payload: SignUpRequest,
    cognito: Annotated[CognitoClient, Depends(get_cognito_client)],
) -> UserResponse:
    email = str(payload.email).lower()

    try:
        user_id = cognito.create_user(email=email, password=payload.password)
    except UserAlreadyExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from error
    except InvalidUserPasswordError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password does not meet the account security requirements.",
        ) from error
    except CognitoRateLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again shortly.",
        ) from error
    except CognitoClientError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The account service is temporarily unavailable.",
        ) from error

    return UserResponse(user_id=user_id, email=email)


@router.post("/guest", response_model=GuestSessionResponse)
def sign_in_as_guest(
    cognito: Annotated[CognitoClient, Depends(get_cognito_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GuestSessionResponse:
    try:
        result = cognito.authenticate_user(
            email=str(settings.guest_email),
            password=settings.guest_password.get_secret_value(),
        )
        access_token, expires_in = _authentication_result(result)
        refresh_token = result.get("RefreshToken")
        id_token = result.get("IdToken")
        if not isinstance(refresh_token, str) or not isinstance(id_token, str):
            raise CognitoAuthenticationError
        claims = jwt.decode(access_token, options={"verify_signature": False})
        user_id = claims.get("sub")
        if not isinstance(user_id, str) or not user_id:
            raise CognitoAuthenticationError
    except CognitoRateLimitError as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Guest access is busy. Please try again shortly.",
        ) from error
    except (CognitoClientError, PyJWTError) as error:
        raise _guest_authentication_unavailable() from error

    return GuestSessionResponse(
        user_id=user_id,
        email=settings.guest_email,
        access_token=access_token,
        id_token=id_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )
