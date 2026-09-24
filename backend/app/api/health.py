from fastapi import APIRouter

from app.services.health import check_health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Unauthenticated liveness/readiness check. Returns statuses only, no paths or versions."""
    return check_health()
