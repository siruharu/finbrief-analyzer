from fastapi import APIRouter
from pydantic import BaseModel

from finbrief_analyzer import __version__
from finbrief_analyzer.core.config import get_settings

router = APIRouter()


class Health(BaseModel):
    status: str
    name: str
    version: str


@router.get("/health", response_model=Health)
def health() -> Health:
    settings = get_settings()
    return Health(status="ok", name=settings.name, version=__version__)
