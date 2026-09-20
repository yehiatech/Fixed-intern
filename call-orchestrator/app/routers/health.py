"""GET /health — used by docker-compose healthcheck and CI/CD to verify the
container is up before Person 1's pipeline proceeds."""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    logger.debug("Health check hit")
    return {"status": "ok"}