import logging

from fastapi import FastAPI

from finbrief_analyzer import __version__
from finbrief_analyzer.api.routes import router
from finbrief_analyzer.core.config import get_settings


def create_app() -> FastAPI:
    """Factory so tests can build an isolated app instance."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(title=settings.name, version=__version__)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower())


if __name__ == "__main__":
    main()
