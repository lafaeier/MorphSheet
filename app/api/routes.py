"""API 路由 — Phase 0 占位，后续 Phase 逐步实现。"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}
