import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.types import utcnow
from app.models.approval import Approval
from app.models.tool_execution import ToolExecution


class ApprovalEngine:
    """Creates Approval records for tool calls that need a human in the loop, and lets the
    orchestrator's run loop suspend until a decision arrives via the API.

    Phase 0 is single-process, so pending decisions live in memory as asyncio.Futures keyed by
    approval id. A restart loses in-flight approvals (the Approval row itself survives in the
    DB as "pending", but nothing is awaiting it anymore) - moving this to a durable queue is
    explicitly a later-phase concern (see spec's "Background Workers").
    """

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}

    async def request_approval(
        self,
        db: AsyncSession,
        *,
        execution: ToolExecution,
        agent_run_id: str,
        reason: str,
    ) -> Approval:
        approval = Approval(
            tool_execution_id=execution.id,
            agent_run_id=agent_run_id,
            risk_level=execution.risk_level,
            reason=reason,
            status="pending",
        )
        db.add(approval)
        await db.flush()
        execution.approval_id = approval.id
        await db.commit()
        await db.refresh(approval)
        self._pending[approval.id] = asyncio.get_running_loop().create_future()
        return approval

    async def wait_for_decision(self, approval_id: str) -> str:
        future = self._pending.get(approval_id)
        if future is None:
            return "denied"
        return await future

    def resolve(self, approval_id: str, decision: str) -> bool:
        future = self._pending.pop(approval_id, None)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    @staticmethod
    def mark_decided(approval: Approval, *, decision: str, decided_by: str) -> None:
        approval.status = decision
        approval.decided_by = decided_by
        approval.decided_at = utcnow()


approval_engine = ApprovalEngine()
