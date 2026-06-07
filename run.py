import sys
import os
import threading
import uvicorn
from app.config import settings


def start_server():
    """在后台线程启动 FastAPI 服务。"""
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level="info",
    )


def start_window():
    """打开 PyWebView 桌面窗口。"""
    import webview
    url = f"http://{settings.host}:{settings.port}"
    webview.create_window(
        title="MorphSheet - 跨系统表格数据转换智能体",
        url=url,
        width=1400,
        height=900,
        min_size=(1024, 680),
    )
    webview.start()


if __name__ == "__main__":
    # 确保数据目录存在
    os.makedirs(os.path.join(settings.data_dir, "uploads"), exist_ok=True)
    os.makedirs(os.path.join(settings.data_dir, "outputs"), exist_ok=True)

    # 启动后端服务
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(1)  # 等待服务启动

    # 启动桌面窗口
    start_window()
