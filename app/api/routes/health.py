from fastapi import APIRouter

from app.runtime.bootstrap import runtime_status

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict[str, str | bool]:
    return {"status": "ok", **runtime_status()}
