"""HTTP adapter for the first local vertical slice."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from .contracts import Catalog, CreateRun, CreateSubmission, EvaluationResult, Run, RunError, Submission
from .demo_catalog import CATALOG, DATASET_ID, RULES_VERSION
from .jobs import IdempotencyConflict, JobStore, local_database


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.body = RunError(code=code, message=message)


def job_store(request: Request) -> JobStore:
    return request.app.state.jobs


def create_app(database: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.jobs = JobStore(database if database is not None else local_database())
        yield

    app = FastAPI(title="AgentQuant", version="0.1.0", lifespan=lifespan)
    store = Annotated[JobStore, Depends(job_store)]
    prefix = "/api/v1"
    not_found = {404: {"model": RunError}}

    @app.exception_handler(ApiError)
    async def handle_error(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.body.model_dump())

    @app.get(f"{prefix}/catalog", operation_id="getCatalog")
    def catalog() -> Catalog:
        return CATALOG

    @app.get(f"{prefix}/submissions", operation_id="listSubmissions")
    def submissions(jobs: store) -> list[Submission]:
        return jobs.list_submissions()

    @app.post(f"{prefix}/submissions", status_code=201, operation_id="createSubmission", responses=not_found)
    def create_submission(data: CreateSubmission, jobs: store) -> Submission:
        if data.source.baseline_id not in {entry.id for entry in CATALOG.baselines}:
            raise ApiError(404, "BASELINE_NOT_FOUND", "该示例策略不存在")
        return jobs.create_submission(data)

    @app.post(f"{prefix}/runs", status_code=202, operation_id="createRun",
              responses={**not_found, 409: {"model": RunError}})
    def create_run(
        data: CreateRun, jobs: store,
        key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=100)],
    ) -> Run:
        if data.dataset_id != DATASET_ID:
            raise ApiError(404, "DATASET_NOT_FOUND", "该样例数据集不存在")
        try:
            run = jobs.create_run(data, key, RULES_VERSION)
        except IdempotencyConflict:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "相同请求标识已用于不同的请求") from None
        if run is None:
            raise ApiError(404, "SUBMISSION_NOT_FOUND", "该提交不存在")
        return run

    @app.get(f"{prefix}/runs/{{run_id}}", operation_id="getRun", responses=not_found)
    def run_status(run_id: UUID, jobs: store) -> Run:
        entry = jobs.get_run(run_id)
        if entry is None:
            raise ApiError(404, "RUN_NOT_FOUND", "该验证任务不存在")
        return entry[0]

    @app.get(f"{prefix}/runs/{{run_id}}/result", operation_id="getResult",
             responses={**not_found, 409: {"model": RunError}})
    def run_result(run_id: UUID, jobs: store) -> EvaluationResult:
        entry = jobs.get_run(run_id)
        if entry is None:
            raise ApiError(404, "RUN_NOT_FOUND", "该验证任务不存在")
        if entry[1] is None:
            raise ApiError(409, "RESULT_UNAVAILABLE", "该任务暂无成功结果")
        return entry[1]

    return app


app = create_app()


def export_openapi(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Export the current HTTP API contract.")
    parser.add_argument("output", type=Path)
    export_openapi(parser.parse_args().output)
