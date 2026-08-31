import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import mask_secrets
from app.models.system_event import SystemEvent


def _redact(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively mask secret-shaped strings before an event is persisted or broadcast."""
    redacted: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            redacted[key] = mask_secrets(value)
        elif isinstance(value, dict):
            redacted[key] = _redact(value)
        else:
            redacted[key] = value
    return redacted


class EventBus:
    """Persists every system event (spec section 19/56: nothing important happens without a
    record) and fans it out to whatever WebSocket connections are subscribed to a project.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    def unsubscribe(self, project_id: str, queue: asyncio.Queue) -> None:
        subscribers = self._subscribers.get(project_id)
        if subscribers:
            subscribers.discard(queue)

    async def publish(
        self,
        session_maker: async_sessionmaker,
        *,
        project_id: str | None,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_run_id: str | None = None,
    ) -> SystemEvent:
        safe_payload = _redact(payload or {})
        event = SystemEvent(
            project_id=project_id,
            agent_run_id=agent_run_id,
            event_type=event_type,
            payload=safe_payload,
        )
        async with session_maker() as db:
            db.add(event)
            await db.commit()

        if project_id:
            message = {
                "id": event.id,
                "type": event.event_type,
                "payload": event.payload,
                "agent_run_id": event.agent_run_id,
                "created_at": event.created_at.isoformat(),
            }
            for queue in list(self._subscribers.get(project_id, [])):
                queue.put_nowait(message)
        return event


event_bus = EventBus()
