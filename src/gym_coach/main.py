from fastapi import FastAPI

from gym_coach.api.health import router as health_router
from gym_coach.api.metrics import router as metrics_router


def create_app() -> FastAPI:
    app = FastAPI(title="gym-coach", version="0.1.0")
    app.include_router(health_router)
    app.include_router(metrics_router)
    return app


app = create_app()
