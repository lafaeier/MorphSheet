from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from app.api.routes import router as api_router

app = FastAPI(title="MorphSheet", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 路由必须在 StaticFiles 之前注册，确保 /api/* 不被静态文件覆盖
app.include_router(api_router, prefix="/api")

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
