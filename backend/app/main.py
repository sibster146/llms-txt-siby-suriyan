from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.configs.config import get_settings
from app.routes import account_management, health

settings = get_settings()

app = FastAPI(
    title="llms.txt API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(health.router)
app.include_router(account_management.router)
