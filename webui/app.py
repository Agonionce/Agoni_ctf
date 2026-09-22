"""FastAPI application for the loopback-only R14 challenge workbench."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agent.challenge.validator import ChallengeValidationError
from agent.runtime.supervision import SupervisedRunCoordinator
from webui.models import (
    CandidateReviewRequest,
    ChallengeCollection,
    ChallengeDetail,
    ChallengeDocuments,
    ChallengeOutcomes,
    DecisionRequest,
    ErrorResponse,
    ExperienceCandidateCollection,
    ExperienceCandidateView,
    HealthResponse,
    RunView,
)
from webui.projections import ChallengeProjectionService
from webui.service import (
    ChallengeCatalogService,
    DuplicateChallengeError,
    UISettings,
)
from webui.uploads import UploadSession, UploadValidationError


ALLOWED_ORIGIN_HOSTS = frozenset({"127.0.0.1", "localhost"})


def create_app(
    settings: UISettings | None = None,
    *,
    run_coordinator: SupervisedRunCoordinator | None = None,
    projection_service: ChallengeProjectionService | None = None,
) -> FastAPI:
    resolved = (settings or UISettings()).normalized()
    service = ChallengeCatalogService(resolved)
    coordinator = run_coordinator or SupervisedRunCoordinator(
        workspace_root=resolved.workspace_root,
        challenge_root=resolved.experience_root,
        checkpoint_root=resolved.checkpoint_root,
        global_experience_path=resolved.global_experience_path,
    )
    projections = projection_service or ChallengeProjectionService(resolved)
    application = FastAPI(
        title="Agonionce Local UI",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    application.state.settings = resolved
    application.state.catalog = service
    application.state.run_coordinator = coordinator
    application.state.projections = projections
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )

    @application.middleware("http")
    async def protect_origin(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme not in {"http", "https"}
                    or parsed.hostname not in ALLOWED_ORIGIN_HOSTS
                ):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "code": "origin_denied",
                            "message": "请求来源不是本地界面",
                        },
                    )
        return await call_next(request)

    @application.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/api/challenges", response_model=ChallengeCollection)
    async def list_challenges() -> ChallengeCollection:
        return ChallengeCollection(items=service.list())

    @application.get("/api/challenges/{challenge_id}", response_model=ChallengeDetail)
    async def get_challenge(challenge_id: str) -> ChallengeDetail:
        challenge = service.get(challenge_id)
        if challenge is None:
            raise HTTPException(status_code=404, detail="未找到该题目")
        return challenge

    @application.post(
        "/api/challenges",
        response_model=ChallengeDetail,
        status_code=status.HTTP_201_CREATED,
        responses={400: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    async def create_challenge(
        name: str = Form(...),
        description: str = Form(...),
        domain: str = Form("auto"),
        target_url: str = Form(""),
        authorization_confirmed: bool = Form(False),
        attachments: list[UploadFile] | None = File(None),
        source_files: list[UploadFile] | None = File(None),
    ) -> ChallengeDetail | JSONResponse:
        if not authorization_confirmed:
            return _error(400, "authorization_required", "请先确认题目属于已授权范围")
        uploads = [*(attachments or []), *(source_files or [])]
        if len(uploads) > resolved.max_uploads:
            return _error(400, "too_many_files", "上传文件数量过多")
        try:
            with UploadSession(resolved) as staged:
                staged_attachments = await staged.stage_many(
                    attachments or [],
                    group="attachments",
                )
                staged_sources = await staged.stage_many(
                    source_files or [],
                    group="sources",
                )
                return service.create(
                    name=name,
                    description=description,
                    domain=domain,
                    target_url=target_url.strip() or None,
                    source_root=staged.root,
                    attachments=staged_attachments,
                    source_files=staged_sources,
                )
        except DuplicateChallengeError as error:
            return _error(
                409,
                "duplicate_challenge",
                "同名题目已存在，可以进入原题继续使用",
                existing_challenge_id=error.challenge_id,
            )
        except UploadValidationError as error:
            return _error(400, "upload_rejected", str(error))
        except ChallengeValidationError as error:
            return _error(400, "challenge_rejected", _friendly_validation(error))
        except (OSError, UnicodeError):
            return _error(
                400,
                "intake_failed",
                "题目材料无法导入，请检查文件后重试",
            )

    @application.get("/api/challenges/{challenge_id}/run", response_model=RunView)
    async def get_run(challenge_id: str) -> RunView:
        try:
            return _run_view(coordinator.view(challenge_id))
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_safe_runtime_error(error)) from error

    @application.post(
        "/api/challenges/{challenge_id}/runs",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def start_run(challenge_id: str) -> RunView | JSONResponse:
        try:
            return _run_view(coordinator.start(challenge_id))
        except ValueError as error:
            return _error(400, "run_not_started", _safe_runtime_error(error))
        except (OSError, RuntimeError, TypeError, KeyError):
            return _error(503, "runtime_unavailable", "运行环境暂时不可用，请检查本地配置后重试")

    @application.post(
        "/api/challenges/{challenge_id}/runs/resume",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def resume_run(challenge_id: str) -> RunView | JSONResponse:
        try:
            return _run_view(coordinator.start(challenge_id, resume=True))
        except ValueError as error:
            return _error(400, "run_not_resumed", _safe_runtime_error(error))
        except (OSError, RuntimeError, TypeError, KeyError):
            return _error(503, "runtime_unavailable", "运行环境暂时不可用，请检查本地配置后重试")

    @application.post(
        "/api/challenges/{challenge_id}/run/decisions/{decision_id}",
        response_model=RunView,
    )
    async def decide_run(
        challenge_id: str,
        decision_id: str,
        body: DecisionRequest,
    ) -> RunView | JSONResponse:
        try:
            return _run_view(
                coordinator.decide(
                    challenge_id,
                    decision_id,
                    approved=body.decision == "approve",
                )
            )
        except ValueError as error:
            return _error(409, "decision_stale", _safe_runtime_error(error))

    @application.post(
        "/api/challenges/{challenge_id}/run/abort",
        response_model=RunView,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def abort_run(challenge_id: str) -> RunView | JSONResponse:
        try:
            return _run_view(coordinator.abort(challenge_id))
        except ValueError as error:
            return _error(409, "run_not_active", _safe_runtime_error(error))

    @application.get(
        "/api/challenges/{challenge_id}/outcomes",
        response_model=ChallengeOutcomes,
    )
    async def get_outcomes(challenge_id: str) -> ChallengeOutcomes:
        try:
            return projections.outcomes(challenge_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_safe_projection_error(error)) from error

    @application.get(
        "/api/challenges/{challenge_id}/documents",
        response_model=ChallengeDocuments,
    )
    async def get_documents(challenge_id: str) -> ChallengeDocuments:
        try:
            return projections.documents(challenge_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_safe_projection_error(error)) from error

    @application.get(
        "/api/challenges/{challenge_id}/experience-candidates",
        response_model=ExperienceCandidateCollection,
    )
    async def get_candidates(challenge_id: str) -> ExperienceCandidateCollection:
        try:
            return projections.candidates(challenge_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=_safe_projection_error(error)) from error

    @application.post(
        "/api/challenges/{challenge_id}/experience-candidates/{candidate_id}",
        response_model=ExperienceCandidateView,
    )
    async def review_candidate(
        challenge_id: str,
        candidate_id: str,
        body: CandidateReviewRequest,
    ) -> ExperienceCandidateView | JSONResponse:
        try:
            return projections.review_candidate(
                challenge_id,
                candidate_id,
                approved=body.decision == "approve",
            )
        except ValueError as error:
            return _error(409, "candidate_not_reviewed", _safe_projection_error(error))

    frontend = Path(__file__).parent / "frontend" / "dist"
    if frontend.is_dir():
        application.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")

    return application


def _friendly_validation(error: Exception) -> str:
    message = str(error)
    replacements = {
        "challenge name must contain visible text": "题目名称需要包含可识别的文字",
        "name must be a non-empty string": "请填写题目名称",
        "name exceeds the intake size limit": "题目名称过长",
        "description must be a non-empty string": "请填写题目描述",
        "description exceeds the intake size limit": "题目描述过长",
        "target_url must be an absolute HTTP(S) URL": (
            "目标地址需要是完整的 HTTP(S) 地址"
        ),
        "target_url must not contain credentials": "目标地址中不能包含账号或密码",
        "target_url contains sensitive data": "目标地址中包含不应导入的敏感值",
        "description contains sensitive data": "题目描述中包含不应导入的敏感值",
        "name contains sensitive data": "题目名称中包含不应导入的敏感值",
    }
    if message in replacements:
        return replacements[message]
    if message.startswith("refusing to import sensitive file:"):
        return "该文件可能包含敏感信息，请移除后重试"
    if message.startswith("domain must be one of:"):
        return "题目领域无效，请重新选择"
    if message.startswith("challenge name already exists:"):
        return "同名题目已存在，请进入原题继续使用"
    return "题目内容未通过安全检查，请调整后重试"


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    existing_challenge_id: str | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        code=code,
        message=message,
        existing_challenge_id=existing_challenge_id,
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _run_view(value: object) -> RunView:
    return RunView.model_validate(value, from_attributes=True)


def _safe_runtime_error(error: Exception) -> str:
    message = str(error)
    allowed = {
        "未找到该题目",
        "该题正在分析中",
        "没有可恢复的安全存档",
        "存档不属于该题目",
        "当前结果不需要恢复",
        "当前没有等待确认的操作",
        "确认项已经变化，请刷新后重试",
        "该确认项已经处理",
        "当前没有正在进行的分析",
    }
    return message if message in allowed else "运行请求未能完成，请检查本地配置后重试"


def _safe_projection_error(error: Exception) -> str:
    message = str(error)
    allowed = {
        "未找到该题目",
        "题目成果暂时无法读取",
        "题目成果格式无效",
        "题目成果不属于当前题目",
        "未找到该经验候选项",
        "rejected candidate cannot be approved",
        "approved candidate cannot be rejected",
    }
    translations = {
        "rejected candidate cannot be approved": "已忽略的经验不能再次纳入",
        "approved candidate cannot be rejected": "已纳入的经验不能再次忽略",
    }
    if message in translations:
        return translations[message]
    return message if message in allowed else "当前内容无法读取，请稍后重试"


app = create_app()
