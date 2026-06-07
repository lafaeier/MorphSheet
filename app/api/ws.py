from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# 存储活跃的 WebSocket 连接: task_id → WebSocket
_active_connections: dict[str, WebSocket] = {}


@router.websocket("/agent-status/{task_id}")
async def agent_status(ws: WebSocket, task_id: str):
    await ws.accept()
    _active_connections[task_id] = ws
    try:
        while True:
            # 保持连接，等待客户端消息（用于心跳/确认）
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        _active_connections.pop(task_id, None)


async def send_to_task(task_id: str, message: dict):
    """向指定任务的 WebSocket 连接发送消息。"""
    ws = _active_connections.get(task_id)
    if ws:
        try:
            await ws.send_json(message)
        except Exception:
            _active_connections.pop(task_id, None)
