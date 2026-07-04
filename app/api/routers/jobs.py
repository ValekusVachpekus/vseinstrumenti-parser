from __future__ import annotations

from arq.jobs import Job
from fastapi import APIRouter

from app.api.deps import ArqDep, TenantDep
from app.api.schemas import JobOut

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, tenant: TenantDep, arq: ArqDep):
    job = Job(job_id, redis=arq)
    status = await job.status()
    result: dict | None = None
    try:
        info = await job.result_info()
        if info is not None and isinstance(info.result, dict):
            result = info.result
    except Exception:  # noqa: BLE001 - result not ready or not serializable
        result = None
    return JobOut(job_id=job_id, status=str(status.value), result=result)
