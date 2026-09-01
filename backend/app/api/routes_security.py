from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.control_assessment import AssessmentResult, ControlAssessment, SecurityControl
from app.models.security_finding import FindingStatus, SecurityFinding, Severity
from app.models.user import User
from app.security import frameworks

router = APIRouter(tags=["security"])


class FindingResponse(BaseModel):
    id: str
    project_id: str
    source: str
    external_id: str | None
    cve_id: str | None
    title: str
    description: str
    severity: str
    status: str
    component: str | None
    file_path: str | None
    evidence: str
    remediation: str
    known_exploited: bool
    epss_score: float | None

    class Config:
        from_attributes = True


class CoverageResponse(BaseModel):
    """Deliberately reports what was *not* determined alongside what passed. A coverage figure
    that hides unknowns is the number that lets an automated reviewer look compliant."""

    framework: str
    version: str
    total_controls: int
    assessed: int
    by_result: dict[str, int]
    automatable: int
    needs_human: int


@router.get("/security/findings", response_model=list[FindingResponse])
async def list_findings(
    project_id: str | None = None,
    status: str | None = FindingStatus.OPEN,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[SecurityFinding]:
    query = select(SecurityFinding)
    if project_id:
        query = query.where(SecurityFinding.project_id == project_id)
    if status:
        query = query.where(SecurityFinding.status == status)

    rows = list((await db.execute(query)).scalars().all())
    # Worst first, and anything being exploited in the wild above everything else.
    rows.sort(key=lambda f: (not f.known_exploited, Severity.rank(f.severity), -(f.epss_score or 0)))
    return rows


@router.get("/security/coverage", response_model=CoverageResponse)
async def coverage(
    project_id: str,
    framework: str = "OWASP-ASVS",
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> CoverageResponse:
    controls = list(
        (await db.execute(select(SecurityControl).where(SecurityControl.framework == framework)))
        .scalars()
        .all()
    )
    if not controls:
        raise HTTPException(status_code=404, detail=f"{framework} has not been imported yet")

    results = dict(
        (
            await db.execute(
                select(ControlAssessment.result, func.count())
                .where(ControlAssessment.project_id == project_id)
                .group_by(ControlAssessment.result)
            )
        ).all()
    )

    needs_human = sum(1 for c in controls if c.verification == ["human_review"])
    return CoverageResponse(
        framework=framework,
        version=controls[0].framework_version,
        total_controls=len(controls),
        assessed=sum(results.values()),
        by_result={r: results.get(r, 0) for r in AssessmentResult.ALL},
        automatable=len(controls) - needs_human,
        needs_human=needs_human,
    )


@router.post("/security/frameworks/import")
async def import_framework(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """Pull the current ASVS release and normalise it into the control catalogue."""
    document = await frameworks.fetch_asvs()
    return await frameworks.import_controls(db, frameworks.parse_asvs(document))
