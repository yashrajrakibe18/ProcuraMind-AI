from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis,
    assistant,
    auth,
    documents,
    health,
    platform,
    projects,
    reports,
    requirements,
    vendors,
)

api_router = APIRouter()
for module in (health, auth, projects, documents, requirements, vendors, analysis, assistant, reports, platform):
    api_router.include_router(module.router)
