from typing import Any

from sqlalchemy import delete, select

from app.agents.roles import ROLES
from app.models.project import Project, ProjectStatus
from app.models.project_task import ProjectTask, TaskStatus
from app.policies.risk import RiskLevel
from app.tools.base import Tool, ToolContext

MAX_TASKS = 30
PLANNABLE_ROLES = ("architect", "coder", "reviewer")


class PlanSubmitTool(Tool):
    name = "plan.submit"
    # READ risk on purpose. A submitted plan is a *proposal*: the rows it writes are inert and
    # nothing executes until a human approves the plan at the plan gate. Charging tool-level
    # approval here would make the human approve the same plan twice - once to let the Manager
    # write it down, once to actually accept it - and the second gate is the meaningful one.
    risk_level = RiskLevel.READ
    description = (
        "Submit your plan for human approval. Give the ordered list of tasks, each with the "
        "role that should carry it out. Nothing runs until a human approves the plan; "
        "submitting replaces any previous unapproved plan for this project."
    )

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        tasks = params.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return {"error": "tasks must be a non-empty list"}
        if len(tasks) > MAX_TASKS:
            return {"error": f"too many tasks: {len(tasks)} (max {MAX_TASKS})"}

        cleaned: list[dict[str, Any]] = []
        for i, raw in enumerate(tasks):
            if not isinstance(raw, dict):
                return {"error": f"task {i} is not an object"}
            title = (raw.get("title") or "").strip()
            if not title:
                return {"error": f"task {i} has no title"}
            role = (raw.get("role") or "").strip().lower()
            if role not in PLANNABLE_ROLES:
                return {
                    "error": (
                        f"task {i} ('{title}') has role '{role or 'none'}'. "
                        f"Plannable roles are: {', '.join(PLANNABLE_ROLES)}"
                    )
                }
            cleaned.append(
                {
                    "title": title[:255],
                    "description": (raw.get("description") or "").strip(),
                    "role": role,
                    "estimated_cost_usd": _as_float(raw.get("estimated_cost_usd")),
                }
            )

        if not any(t["role"] == "reviewer" for t in cleaned):
            return {
                "error": (
                    "this plan has no reviewer task. Every piece of implementation must be "
                    "reviewed - add reviewer tasks and submit again."
                )
            }

        async with ctx.session_maker() as db:
            project = await db.get(Project, ctx.project_id)
            if project is None:
                return {"error": "project not found"}
            if project.status == ProjectStatus.EXECUTING:
                return {"error": "this project's plan is already approved and running"}

            # Replace any earlier unapproved proposal rather than appending to it, so a
            # resubmitted plan is the whole plan and not a second copy of half of it.
            await db.execute(delete(ProjectTask).where(ProjectTask.project_id == ctx.project_id))
            for index, task in enumerate(cleaned):
                db.add(
                    ProjectTask(
                        project_id=ctx.project_id,
                        order_index=index,
                        title=task["title"],
                        description=task["description"],
                        assigned_role=task["role"],
                        status=TaskStatus.PENDING,
                        estimated_cost_usd=task["estimated_cost_usd"],
                    )
                )
            project.status = ProjectStatus.PLAN_PROPOSED
            await db.commit()

        total = sum(t["estimated_cost_usd"] or 0.0 for t in cleaned)
        return {
            "submitted": True,
            "task_count": len(cleaned),
            "estimated_total_usd": round(total, 6) if total else None,
            "tasks": [{"order": i, "title": t["title"], "role": t["role"]} for i, t in enumerate(cleaned)],
            "status": "awaiting human approval - nothing will run until the plan is approved",
        }


class PlanReadTool(Tool):
    name = "plan.read"
    risk_level = RiskLevel.READ
    description = "Read the current plan for this project: its tasks, roles and statuses."

    async def execute(self, ctx: ToolContext, params: dict[str, Any]) -> dict[str, Any]:
        async with ctx.session_maker() as db:
            project = await db.get(Project, ctx.project_id)
            result = await db.execute(
                select(ProjectTask)
                .where(ProjectTask.project_id == ctx.project_id)
                .order_by(ProjectTask.order_index)
            )
            tasks = list(result.scalars().all())

        return {
            "project_status": project.status if project else None,
            "tasks": [
                {
                    "order": t.order_index,
                    "title": t.title,
                    "description": t.description,
                    "role": t.assigned_role,
                    "status": t.status,
                    "attempts": t.attempts,
                    "review_notes": t.review_notes,
                }
                for t in tasks
            ],
        }


def _as_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


PLAN_TOOL_SCHEMAS: dict[str, dict] = {
    "plan.read": {},
    "plan.submit": {
        "tasks": {
            "type": "array",
            "description": "the ordered tasks that make up the plan",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "short imperative title"},
                    "description": {
                        "type": "string",
                        "description": "what to do, specific enough for the assigned role to act on alone",
                    },
                    "role": {
                        "type": "string",
                        "enum": list(PLANNABLE_ROLES),
                        "description": "which role carries out this task",
                    },
                    "estimated_cost_usd": {
                        "type": "number",
                        "description": "cost for this task from cost.estimate",
                    },
                },
                "required": ["title", "description", "role"],
            },
        }
    },
}

assert set(PLANNABLE_ROLES) <= set(ROLES), "plannable roles must all exist in the roster"
