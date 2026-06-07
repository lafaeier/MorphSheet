import sys
import os
import threading
import urllib.request
import uvicorn
from app.config import settings


VUE_URLS = [
    "https://cdn.jsdelivr.net/npm/vue@3/dist/vue.global.prod.js",
    "https://unpkg.com/vue@3/dist/vue.global.prod.js",
    "https://cdn.bootcdn.net/ajax/libs/vue/3.4.21/vue.global.prod.js",
]


def ensure_local_vue():
    """确保本地有 Vue.js 文件。首次启动时从 CDN 下载。"""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    vue_path = os.path.join(static_dir, "vue.global.prod.js")

    if os.path.exists(vue_path) and os.path.getsize(vue_path) > 10000:
        return True  # 已有有效文件

    print("[Setup] Downloading Vue.js locally...")
    for url in VUE_URLS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MorphSheet/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) > 10000:
                with open(vue_path, "wb") as f:
                    f.write(data)
                print(f"[Setup] Vue.js downloaded ({len(data)} bytes) from {url}")
                return True
        except Exception as e:
            print(f"[Setup] Failed: {url} - {e}")
            continue

    print("[Setup] WARNING: Could not download Vue.js. Will rely on CDN at runtime.")
    return False


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

    # 首次启动：下载 Vue.js 到本地
    ensure_local_vue()

    # 启动后端服务
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(1.5)

    # 启动桌面窗口
    start_window()
