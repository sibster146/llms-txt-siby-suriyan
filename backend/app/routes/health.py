"""Expose a lightweight application liveness endpoint without external checks."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Return an unauthenticated OK response without checking AWS dependencies."""
    return {"status": "ok"}
