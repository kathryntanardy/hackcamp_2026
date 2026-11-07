"""HTTP API for the Open-Source Corpus Explorer."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Open-Source Corpus Explorer API", version="0.1.0")


class HealthResponse(BaseModel):
    status: str


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    return HealthResponse(status="ok")
