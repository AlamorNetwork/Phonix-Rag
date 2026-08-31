import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.service import get_agent
from app.core.config import Settings
from app.cost.engine import CostEngine
from app.events.bus import EventBus
from app.models.agent_run import AgentRun
from app.models.project import Project, ProjectStatus
from app.models.project_task import ProjectTask, TaskStatus
from app.orchestrator.runner import AgentRunner
from app.providers.base import ModelProvider
from app.tools.gateway import ToolGateway

logger = logging.getLogger(__name__)

# How many times a coder task may be sent back before the project stops and asks a human.
# Without a ceiling a reviewer that keeps rejecting and a coder that keeps not fixing it will
# burn the budget in a loop (spec section 33: loop protection).
MAX_ATTEMPTS = 3

REJECTED_MARKER = "REJECTED"


class ProjectRunner:
    """Walks an approved plan: takes each task in order, hands it to the role that owns it, and
    routes the result. A reviewer that rejects sends the preceding coder task back with its
    findings rather than letting the plan continue over broken work.
    """

    def __init__(
        self,
        session_maker: async_sessionmaker,
        provider: ModelProvider,
        tool_gateway: ToolGateway,
        event_bus: EventBus,
        cost_engine: CostEngine,
        settings: Settings,
    ):
        self.session_maker = session_maker
        self.provider = provider
        self.tool_gateway = tool_gateway
        self.event_bus = event_bus
        self.cost_engine = cost_engine
        self.settings = settings

    def _agent_runner(self) -> AgentRunner:
        return AgentRunner(
            self.session_maker, self.provider, self.tool_gateway, self.event_bus,
            self.cost_engine, self.settings,
        )

    async def run(self, project_id: str) -> None:
        """Execute the approved plan to completion, or until something needs a human."""
        try:
            await self._execute(project_id)
        except Exception as exc:  # noqa: BLE001 - one project must not take down the process
            logger.exception("project %s execution failed", project_id)
            await self.event_bus.publish(
                self.session_maker, project_id=project_id, event_type="project.failed",
                payload={"detail": f"{type(exc).__name__}: {exc}"},
            )

    async def _execute(self, project_id: str) -> None:
        while True:
            task = await self._next_task(project_id)
            if task is None:
                break

            outcome = await self._run_task(project_id, task)
            if outcome == "blocked":
                await self.event_bus.publish(
                    self.session_maker, project_id=project_id, event_type="project.blocked",
                    payload={"task_id": task["id"], "title": task["title"]},
                )
                return

        async with self.session_maker() as db:
            project = await db.get(Project, project_id)
            if project is not None:
                project.status = ProjectStatus.COMPLETED
                await db.commit()

        await self.event_bus.publish(
            self.session_maker, project_id=project_id, event_type="project.completed", payload={},
        )

    async def _next_task(self, project_id: str) -> dict | None:
        """The lowest-ordered task still to do. Rejected tasks come before pending ones at the
        same position because the rework has to happen before the plan moves on."""
        async with self.session_maker() as db:
            result = await db.execute(
                select(ProjectTask)
                .where(
                    ProjectTask.project_id == project_id,
                    ProjectTask.status.in_([TaskStatus.PENDING, TaskStatus.REJECTED]),
                )
                .order_by(ProjectTask.order_index)
            )
            task = result.scalars().first()
            if task is None:
                return None
            return {
                "id": task.id,
                "title": task.title,
                "description": task.description,
                "role": task.assigned_role,
                "order_index": task.order_index,
                "attempts": task.attempts,
                "review_notes": task.review_notes,
            }

    async def _run_task(self, project_id: str, task: dict) -> str:
        if task["attempts"] >= MAX_ATTEMPTS:
            await self._set_status(task["id"], TaskStatus.BLOCKED)
            return "blocked"

        async with self.session_maker() as db:
            agent = await get_agent(db, project_id, task["role"])
            if agent is None:
                await self._set_status(task["id"], TaskStatus.BLOCKED)
                return "blocked"
            agent_id = agent.id

            run = AgentRun(
                agent_id=agent_id,
                project_id=project_id,
                status="queued",
                input_message=self._instructions(task),
            )
            db.add(run)

            db_task = await db.get(ProjectTask, task["id"])
            db_task.status = TaskStatus.RUNNING
            db_task.attempts += 1
            await db.commit()
            await db.refresh(run)
            run_id = run.id

        async with self.session_maker() as db:
            db_task = await db.get(ProjectTask, task["id"])
            db_task.agent_run_id = run_id
            await db.commit()

        await self.event_bus.publish(
            self.session_maker, project_id=project_id, agent_run_id=run_id,
            event_type="task.started",
            payload={"task_id": task["id"], "title": task["title"], "role": task["role"]},
        )

        await self._agent_runner().run(run_id)

        async with self.session_maker() as db:
            finished = await db.get(AgentRun, run_id)
            run_status = finished.status
            output = finished.output_message or ""

        if run_status != "completed":
            await self._set_status(task["id"], TaskStatus.BLOCKED)
            await self.event_bus.publish(
                self.session_maker, project_id=project_id, agent_run_id=run_id,
                event_type="task.blocked",
                payload={"task_id": task["id"], "reason": run_status, "detail": output[:500]},
            )
            return "blocked"

        if task["role"] == "reviewer" and _is_rejection(output):
            return await self._handle_rejection(project_id, task, output, run_id)

        await self._set_status(task["id"], TaskStatus.DONE)
        await self.event_bus.publish(
            self.session_maker, project_id=project_id, agent_run_id=run_id,
            event_type="task.completed",
            payload={"task_id": task["id"], "title": task["title"], "role": task["role"]},
        )
        return "done"

    async def _handle_rejection(self, project_id: str, task: dict, output: str, run_id: str) -> str:
        """A rejection reopens the most recent coder task before this one - that is the work
        being judged - and carries the findings into its next attempt."""
        async with self.session_maker() as db:
            result = await db.execute(
                select(ProjectTask)
                .where(
                    ProjectTask.project_id == project_id,
                    ProjectTask.assigned_role == "coder",
                    ProjectTask.order_index < task["order_index"],
                )
                .order_by(ProjectTask.order_index.desc())
            )
            target = result.scalars().first()

            reviewer_task = await db.get(ProjectTask, task["id"])
            reviewer_task.status = TaskStatus.PENDING
            reviewer_task.review_notes = output[:4000]

            if target is None:
                # Nothing to send back to; don't silently accept the rejection.
                reviewer_task.status = TaskStatus.BLOCKED
                await db.commit()
                return "blocked"

            if target.attempts >= MAX_ATTEMPTS:
                target.status = TaskStatus.BLOCKED
                reviewer_task.status = TaskStatus.BLOCKED
                await db.commit()
                blocked_title = target.title
                await self.event_bus.publish(
                    self.session_maker, project_id=project_id, agent_run_id=run_id,
                    event_type="task.blocked",
                    payload={
                        "task_id": target.id,
                        "title": blocked_title,
                        "reason": f"rejected {target.attempts} times; a human needs to look",
                    },
                )
                return "blocked"

            target.status = TaskStatus.REJECTED
            target.review_notes = output[:4000]
            target_id, target_title = target.id, target.title
            await db.commit()

        await self.event_bus.publish(
            self.session_maker, project_id=project_id, agent_run_id=run_id,
            event_type="task.rejected",
            payload={"task_id": target_id, "title": target_title, "notes": output[:500]},
        )
        return "rejected"

    async def _set_status(self, task_id: str, status: str) -> None:
        async with self.session_maker() as db:
            task = await db.get(ProjectTask, task_id)
            if task is not None:
                task.status = status
                await db.commit()

    def _instructions(self, task: dict) -> str:
        parts = [f"Task: {task['title']}"]
        if task["description"]:
            parts.append(task["description"])
        if task["review_notes"]:
            parts.append(
                "A reviewer sent your previous attempt back. Address every point:\n"
                f"{task['review_notes']}"
            )
        if task["role"] == "reviewer":
            parts.append(
                "Review the work in the workspace against this task. If it is correct, say so "
                f"and explain what you checked. If it is not, begin your reply with the single "
                f"word {REJECTED_MARKER} and then list each finding with its evidence."
            )
        return "\n\n".join(parts)


def _is_rejection(output: str) -> bool:
    """A reviewer signals rejection with a marker as the first word, so the verdict is a
    deliberate act rather than something inferred from prose that merely mentions problems."""
    return output.strip().upper().startswith(REJECTED_MARKER)
