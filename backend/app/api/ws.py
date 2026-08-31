from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import decode_access_token
from app.database.session import async_session_maker
from app.events.bus import event_bus
from app.models.user import User

router = APIRouter()


@router.websocket("/ws/projects/{project_id}")
async def project_events_ws(websocket: WebSocket, project_id: str, token: str | None = None) -> None:
    email = decode_access_token(token) if token else None
    if not email:
        await websocket.close(code=4401)
        return

    async with async_session_maker() as db:
        result = await db.execute(select(User).where(User.email == email))
        if result.scalar_one_or_none() is None:
            await websocket.close(code=4401)
            return

    await websocket.accept()
    queue = event_bus.subscribe(project_id)
    try:
        while True:
            message = await queue.get()
            await websocket.send_json(message)
    except WebSocketDisconnect:
        pass
    finally:
        event_bus.unsubscribe(project_id, queue)
