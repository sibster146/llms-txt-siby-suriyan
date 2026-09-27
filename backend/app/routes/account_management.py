from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.clients.cognito import (
    CognitoClient,
    CognitoClientError,
    CognitoRateLimitError,
    InvalidUserPasswordError,
    UserAlreadyExistsError,
)
from app.configs.dependencies import get_cognito_client
from app.schemas.account_management import SignUpRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


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
