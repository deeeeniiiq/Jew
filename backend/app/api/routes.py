from __future__ import annotations

import asyncio
from hashlib import sha1
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.api.deps import (
    ensure_debug_logs_enabled,
    get_assessment_service,
    get_agent_runtime,
    get_debug_logs,
    get_normalizer,
    get_quiz_service,
    get_repository,
)
from app.api.route_helpers import (
    local_user as _local_user,
    local_workspace_surface as _local_workspace_surface,
    normalize_resource_url as _normalize_resource_url,
    resource_label_from_url as _resource_label_from_url,
    workspace_config_payload as _workspace_config_payload,
)
from app.core.config import Settings, get_settings
from app.models.api import GraphExportRequest, GraphImportRequest, GraphLayoutPositionRequest, LessonGenerateRequest, RenameGraphRequest, TopicArtifactInput, TopicResourceInput, UpdateGraphLayoutRequest
from app.models.domain import Artifact, CreateGraphRequest, GraphProposalEnvelope, LearnerProfile, QuizReportRecord, QuizStartRequest, QuizStartResponse, QuizStudyDraft, QuizSubmitRequest, QuizSubmitResponse, ResourceLink, UpdateWorkspaceConfigRequest
from app.services.roadmap_studio import RoadmapGenerateRequest
from app.services.adaptive_learning import AdaptiveLearningService
from app.services.debug_log_service import DebugClientLogRequest, get_debug_log_service
from app.services.proposal_normalizer import ProposalNormalizer
from app.services.repository import GraphRepository, ProposalConflictError, RepositoryConflictError
from app.services.pdf_export import PDFExportError, render_quiz_report_pdf
from app.agent.chatgpt_auth import ChatGPTError
from app.agent.tools import public_quiz

if TYPE_CHECKING:
    from app.services.quiz_service import QuizService

router = APIRouter()


class RoadmapConfirmRequest(BaseModel):
    ticket: str = Field(min_length=32, max_length=64)


@router.get("/api/v1/learner/profile")
def learner_profile(repository: GraphRepository = Depends(get_repository)) -> LearnerProfile:
    return repository.current().workspace.learner_profile


@router.put("/api/v1/learner/profile")
def save_learner_profile(
    profile: LearnerProfile,
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _workspace_config_payload(repository.save_learner_profile(profile), settings)


@router.post("/api/v1/roadmaps/preview")
async def roadmap_preview(request: RoadmapGenerateRequest, runtime=Depends(get_agent_runtime)) -> dict:
    try:
        return await runtime.preview_roadmap(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatGPTError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/api/v1/roadmaps/confirm")
async def roadmap_confirm(
    request: RoadmapConfirmRequest,
    repository: GraphRepository = Depends(get_repository),
    runtime=Depends(get_agent_runtime),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        preview, original_snapshot_id = runtime.confirmed_roadmap(request.ticket)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    def persist_and_finish() -> object:
        # The SQLite write runs in a worker thread. If the HTTP caller is
        # cancelled, the thread keeps running; only the worker may release its
        # ticket, after the database transaction has actually finished.
        try:
            result = repository.create_roadmap(preview, expected_snapshot_id=original_snapshot_id)
        except BaseException:
            runtime.release_roadmap_preview(request.ticket)
            raise
        runtime.discard_roadmap_preview(request.ticket)
        return result

    pending = asyncio.create_task(asyncio.to_thread(persist_and_finish))

    def observe_completion(task: asyncio.Task) -> None:
        # Retrieve errors if the requesting client disappeared. A task cancelled
        # before it starts still needs its ticket released.
        if task.cancelled():
            runtime.release_roadmap_preview(request.ticket)
        else:
            task.exception()

    pending.add_done_callback(observe_completion)
    try:
        result = await asyncio.shield(pending)
    except (RepositoryConflictError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Auxiliary memory is best effort. A Ruflo outage cannot roll back SQLite.
    try:
        await asyncio.wait_for(runtime.remember_roadmap(preview), timeout=10)
    except (Exception, asyncio.CancelledError):
        pass
    return _workspace_config_payload(result, settings)


@router.get("/healthz")
def healthz(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "ok": True,
        "app": settings.app_name,
        "agent_backend": "ruflo_native | chatgpt | ollama | openai_api | codex_cli",
    }


@router.get("/api/v1/meta/protocol")
def protocol(settings: Settings = Depends(get_settings)) -> dict:
    return {
        "workspace_shape": "many isolated graphs + shared config",
        "topic_states": ["not_started", "learning", "shaky", "solid", "mastered", "needs_review"],
        "edge_relations": ["requires", "supports", "bridges", "extends", "reviews"],
        "proposal_contract": "/contracts/graph_patch.schema.json",
        "agent_backend": "ruflo_native | chatgpt | ollama | openai_api | codex_cli",
        "native_tools_contract": "/contracts/clew_tools.schema.json",
        "guarantees": [
            "topic-first graph",
            "proposal before mutation",
            "snapshot after apply",
            "rollback available",
        ],
    }


@router.get("/api/v1/workspace/current")
def current_workspace(
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    envelope = repository.current()
    return _workspace_config_payload(envelope, settings)


@router.get("/api/v1/workspace/surface")
def workspace_surface(repository: GraphRepository = Depends(get_repository)) -> dict:
    return _local_workspace_surface(repository)


@router.get("/api/v1/auth/session")
def auth_session(
    settings: Settings = Depends(get_settings),
    repository: GraphRepository = Depends(get_repository),
) -> dict:
    return {
        "authenticated": True,
        "user": _local_user(settings),
        "workspace_surface": _local_workspace_surface(repository),
    }


@router.get("/api/v1/debug/logs")
def debug_logs_snapshot(
    _: None = Depends(ensure_debug_logs_enabled),
    debug_logs=Depends(get_debug_logs),
) -> dict:
    return debug_logs.snapshot().model_dump(mode="json")


@router.post("/api/v1/debug/logs/client")
def debug_logs_client_ingest(
    request: DebugClientLogRequest,
    _: None = Depends(ensure_debug_logs_enabled),
    debug_logs=Depends(get_debug_logs),
) -> dict:
    entry = debug_logs.ingest_client_entry(request)
    return {"ok": True, "entry": entry.model_dump(mode="json")}


@router.get("/api/v1/workspace/graphs")
def workspace_graphs(repository: GraphRepository = Depends(get_repository)) -> dict:
    return {
        "items": [summary.model_dump(mode="json") for summary in repository.graph_summaries()],
    }


@router.post("/api/v1/workspace/graphs")
def create_workspace_graph(request: CreateGraphRequest, repository: GraphRepository = Depends(get_repository)) -> dict:
    try:
        workspace = repository.create_graph(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, get_settings())


@router.delete("/api/v1/workspace/graphs/{graph_id}")
async def delete_workspace_graph(graph_id: str, repository: GraphRepository = Depends(get_repository), runtime=Depends(get_agent_runtime)) -> dict:
    for run in list(runtime.runs.values()):
        if run.graph_id == graph_id and not run.done.done():
            await runtime.interrupt_run(run)
    try:
        workspace = repository.delete_graph(graph_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, get_settings())


@router.post("/api/v1/workspace/graphs/{graph_id}/rename")
def rename_workspace_graph(
    graph_id: str,
    request: RenameGraphRequest,
    repository: GraphRepository = Depends(get_repository),
) -> dict:
    try:
        workspace = repository.rename_graph(graph_id, request.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, get_settings())


@router.post("/api/v1/workspace/graphs/{graph_id}/layout")
def update_workspace_graph_layout(
    graph_id: str,
    request: UpdateGraphLayoutRequest,
    repository: GraphRepository = Depends(get_repository),
) -> dict:
    try:
        workspace = repository.update_graph_layout(
            graph_id,
            {topic_id: position.model_dump(mode="json") for topic_id, position in request.positions.items()},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, get_settings())


@router.post("/api/v1/workspace/graphs/{graph_id}/topics/{topic_id}/resources")
def append_topic_resource(
    graph_id: str,
    topic_id: str,
    body: TopicResourceInput,
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    normalized_url = _normalize_resource_url(body.url)
    if not normalized_url:
        raise HTTPException(status_code=400, detail="resource url is required")
    resource = ResourceLink(
        id=f"resource-{sha1(normalized_url.encode('utf-8')).hexdigest()[:12]}",
        label=_resource_label_from_url(normalized_url),
        url=normalized_url,
        kind="link",
    )
    try:
        workspace = repository.append_topic_resource(graph_id, topic_id, resource)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return _workspace_config_payload(workspace, settings)


@router.post("/api/v1/workspace/graphs/{graph_id}/topics/{topic_id}/artifacts")
def append_topic_artifact(
    graph_id: str,
    topic_id: str,
    body: TopicArtifactInput,
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    normalized_title = body.title.strip()
    normalized_body = body.body.strip()
    if not normalized_title:
        raise HTTPException(status_code=400, detail="artifact title is required")
    if not normalized_body:
        raise HTTPException(status_code=400, detail="artifact body is required")
    artifact_id_source = f"{graph_id}:{topic_id}:{normalized_title}:{normalized_body}"
    artifact = Artifact(
        id=f"artifact-{sha1(artifact_id_source.encode('utf-8')).hexdigest()[:12]}",
        title=normalized_title,
        kind="note",
        body=normalized_body,
    )
    try:
        workspace = repository.append_topic_artifact(graph_id, topic_id, artifact)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return _workspace_config_payload(workspace, settings)


@router.post("/api/v1/graphs/{graph_id}/topics/{topic_id}/lessons/generate")
async def generate_topic_lesson(
    graph_id: str,
    topic_id: str,
    request: LessonGenerateRequest,
    runtime=Depends(get_agent_runtime),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        artifact, workspace = await runtime.generate_lesson(graph_id, topic_id, request.model)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Graph or topic not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatGPTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"artifact": artifact.model_dump(mode="json"), "workspace": _workspace_config_payload(workspace, settings)}


@router.post("/api/v1/workspace/graphs/{graph_id}/export")
def export_workspace_graph(
    graph_id: str,
    request: GraphExportRequest,
    repository: GraphRepository = Depends(get_repository),
) -> dict:
    try:
        if request.format == "mapmind_obsidian_export":
            package = repository.export_graph_to_obsidian(
                graph_id,
                title=request.title,
                include_progress=request.include_progress,
                options=request.obsidian,
            )
        else:
            package = repository.export_graph_package(
                graph_id,
                title=request.title,
                include_progress=request.include_progress,
            )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return package.model_dump(mode="json")


@router.post("/api/v1/workspace/graphs/import")
def import_workspace_graph(
    request: GraphImportRequest,
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        workspace = repository.import_graph_package(
            request.package,
            title=request.title,
            include_progress=request.include_progress,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, settings)


@router.post("/api/v1/workspace/config")
def update_workspace_config(
    request: UpdateWorkspaceConfigRequest,
    repository: GraphRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        workspace = repository.update_workspace_config(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(workspace, settings)


@router.get("/api/v1/graphs/{graph_id}")
def graph_by_id(graph_id: str, repository: GraphRepository = Depends(get_repository)) -> dict:
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    return graph.model_dump(mode="json")


@router.get("/api/v1/graphs/{graph_id}/learning-plan")
def graph_learning_plan(
    graph_id: str,
    repository: GraphRepository = Depends(get_repository),
) -> dict:
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    return AdaptiveLearningService().build_plan(graph).model_dump(mode="json")


@router.get("/api/v1/graphs/{graph_id}/assessment")
def graph_assessment(
    graph_id: str,
    repository: GraphRepository = Depends(get_repository),
    assessment_service: AssessmentService = Depends(get_assessment_service),
) -> dict:
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    return assessment_service.assess_graph(graph).model_dump(mode="json")


@router.get("/api/v1/graph/current")
def current_graph(repository: GraphRepository = Depends(get_repository)) -> dict:
    envelope = repository.current()
    graph_id = envelope.workspace.active_graph_id or (envelope.workspace.graphs[0].graph_id if envelope.workspace.graphs else None)
    if graph_id is None:
        raise HTTPException(status_code=404, detail="no graphs found")
    graph = repository.graph(graph_id)
    return graph.model_dump(mode="json")


@router.get("/api/v1/graph/snapshots")
def graph_snapshots(repository: GraphRepository = Depends(get_repository)) -> dict:
    return {
        "items": [record.model_dump(mode="json") for record in repository.list_snapshots()],
    }


@router.post("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/start")
async def start_topic_quiz(
    graph_id: str,
    topic_id: str,
    request: QuizStartRequest,
    repository: GraphRepository = Depends(get_repository),
    runtime=Depends(get_agent_runtime),
    quiz_service: "QuizService" = Depends(get_quiz_service),
) -> dict:
    try:
        graph = repository.graph(graph_id)
        topic = next((item for item in graph.topics if item.id == topic_id), None)
        if topic is None:
            raise KeyError(topic_id)
        question_count = request.question_count or repository.current().workspace.config.quiz_question_count
        session = repository.latest_quiz_session_for_topic(graph_id, topic_id)
        if session is not None:
            try:
                quiz_service.ensure_mathematical_safety(session.questions)
            except ValueError:
                # Keep the historical record intact, but do not serve it again.
                session = None
        if (session is None or session.question_count != question_count
                or (request.model is not None and session.generator != request.model)):
            session = await runtime.generate_closure_quiz(
                graph_id, topic_id, question_count, request.model,
            )
        return QuizStartResponse(session=public_quiz(session)).model_dump(mode="json")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Graph or topic not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ChatGPTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/{session_id}/draft", response_model=QuizStudyDraft)
def get_quiz_study_draft(graph_id: str, topic_id: str, session_id: str,
                         repository: GraphRepository = Depends(get_repository)) -> QuizStudyDraft:
    try:
        return repository.quiz_study_draft(graph_id, topic_id, session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Quiz session not found") from exc


@router.put("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/{session_id}/draft", response_model=QuizStudyDraft)
def put_quiz_study_draft(graph_id: str, topic_id: str, session_id: str, draft: QuizStudyDraft,
                         repository: GraphRepository = Depends(get_repository)) -> QuizStudyDraft:
    try:
        return repository.save_quiz_study_draft(graph_id, topic_id, session_id, draft)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Quiz session not found") from exc
    except RepositoryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/submit")
def submit_topic_quiz(
    graph_id: str,
    topic_id: str,
    request: QuizSubmitRequest,
    repository: GraphRepository = Depends(get_repository),
    quiz_service: "QuizService" = Depends(get_quiz_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    try:
        session = repository.quiz_session(request.session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"quiz session {request.session_id} not found") from exc
    if session.graph_id != graph_id or session.topic_id != topic_id:
        raise HTTPException(status_code=400, detail="quiz session does not match graph/topic route")

    answers = {answer.question_id: answer.choice_index for answer in request.answers}
    if len(answers) != len(request.answers):
        raise HTTPException(status_code=400, detail="A quiz question may only be answered once.")
    try:
        attempt, _, awarded_state, reviews = quiz_service.grade_session(
            graph, session, answers, pass_threshold=repository.current().workspace.config.pass_threshold,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    topic = next(item for item in graph.topics if item.id == topic_id)
    report = quiz_service.build_pedagogical_report(attempt, session, reviews, topic.title)
    workspace = repository.record_quiz_attempt(graph_id, attempt, awarded_state,
                                              base_graph_version=graph.version, session_id=session.session_id,
                                              report=report, reviews=reviews)
    updated_graph = next(item for item in workspace.workspace.graphs if item.graph_id == graph_id)
    closure_status = quiz_service.build_closure_status(updated_graph, topic_id)
    repository.append_event(
        "graph.quiz.submitted",
        {
            "graph_id": graph_id,
            "topic_id": topic_id,
            "session_id": request.session_id,
            "score": attempt.score,
            "passed": attempt.passed,
            "closure_awarded": attempt.closure_awarded,
        },
    )
    return QuizSubmitResponse(
        attempt=attempt,
        closure_status=closure_status,
        awarded_state=awarded_state,
        reviews=reviews,
        report=report,
        workspace=workspace,
    ).model_dump(mode="json") | {"workspace": _workspace_config_payload(workspace, settings)}


@router.get("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports")
def list_topic_quiz_reports(graph_id: str, topic_id: str,
                            limit: int = Query(default=20, ge=1, le=100),
                            offset: int = Query(default=0, ge=0),
                            repository: GraphRepository = Depends(get_repository)) -> dict:
    try:
        return repository.list_quiz_reports(graph_id, topic_id, limit=limit, offset=offset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Graph or topic not found") from exc
    except ValueError as exc:
        if "Unsupported pedagogical report format version" in str(exc):
            raise HTTPException(status_code=409, detail="Stored report uses an unsupported format version") from exc
        raise HTTPException(status_code=500, detail="Stored pedagogical report failed integrity checks") from exc


@router.get("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}")
def get_topic_quiz_report(graph_id: str, topic_id: str, attempt_id: str,
                          repository: GraphRepository = Depends(get_repository)) -> dict:
    try:
        return repository.get_quiz_report(graph_id, topic_id, attempt_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Pedagogical report not found") from exc
    except ValueError as exc:
        if "Unsupported pedagogical report format version" in str(exc):
            raise HTTPException(status_code=409, detail="Stored report uses an unsupported format version") from exc
        raise HTTPException(status_code=500, detail="Stored pedagogical report failed integrity checks") from exc


@router.get("/api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}/pdf")
def download_topic_quiz_report_pdf(graph_id: str, topic_id: str, attempt_id: str,
                                   repository: GraphRepository = Depends(get_repository)) -> Response:
    # Reuse the JSON endpoint's validation, scoping and safe error mapping.
    payload = get_topic_quiz_report(graph_id, topic_id, attempt_id, repository)
    try:
        record = QuizReportRecord.model_validate(payload)
        content = render_quiz_report_pdf(record, in_current_graph=payload["in_current_graph"])
    except (PDFExportError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=500, detail="Pedagogical PDF could not be generated") from exc
    return Response(content=content, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="jew-relatorio-pedagogico.pdf"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/api/v1/graphs/{graph_id}/topics/{topic_id}/mark-finished")
def mark_topic_finished(
    graph_id: str,
    topic_id: str,
    repository: GraphRepository = Depends(get_repository),
    quiz_service: "QuizService" = Depends(get_quiz_service),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        workspace = repository.mark_topic_finished(graph_id, topic_id)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(status_code=404 if "not found" in message else 400, detail=message) from exc

    updated_graph = next(item for item in workspace.workspace.graphs if item.graph_id == graph_id)
    closure_status = quiz_service.build_closure_status(updated_graph, topic_id)
    attempt = next(item for item in reversed(updated_graph.quiz_attempts) if item.topic_id == topic_id)
    repository.append_event(
        "graph.topic.mark_finished",
        {
            "graph_id": graph_id,
            "topic_id": topic_id,
            "score": attempt.score,
            "passed": attempt.passed,
            "closure_awarded": attempt.closure_awarded,
        },
    )
    return QuizSubmitResponse(
        attempt=attempt,
        closure_status=closure_status,
        awarded_state="solid",
        reviews=[],
        workspace=workspace,
    ).model_dump(mode="json") | {"workspace": _workspace_config_payload(workspace, settings)}


@router.post("/api/v1/graphs/{graph_id}/normalize")
def normalize_graph_proposal(
    graph_id: str,
    envelope: GraphProposalEnvelope,
    repository: GraphRepository = Depends(get_repository),
    normalizer: ProposalNormalizer = Depends(get_normalizer),
) -> dict:
    if envelope.graph_id != graph_id:
        raise HTTPException(status_code=400, detail="graph_id in route and payload must match")
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    plan = normalizer.normalize(envelope, graph=graph)
    return plan.model_dump(mode="json")


@router.post("/api/v1/graphs/{graph_id}/apply")
def apply_graph_proposal(
    graph_id: str,
    envelope: GraphProposalEnvelope,
    repository: GraphRepository = Depends(get_repository),
    normalizer: ProposalNormalizer = Depends(get_normalizer),
) -> dict:
    if envelope.graph_id != graph_id:
        raise HTTPException(status_code=400, detail="graph_id in route and payload must match")
    try:
        graph = repository.graph(graph_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"graph {graph_id} not found") from exc
    plan = normalizer.normalize(envelope, graph=graph)
    if not plan.validation.ok:
        raise HTTPException(status_code=400, detail={"errors": plan.validation.errors, "warnings": plan.validation.warnings})
    try:
        applied = repository.apply_proposal(plan.normalized_proposal)
    except ProposalConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _workspace_config_payload(applied, get_settings())


@router.post("/api/v1/graph/rollback/{snapshot_id}")
async def rollback_graph(snapshot_id: int, repository: GraphRepository = Depends(get_repository), runtime=Depends(get_agent_runtime)) -> dict:
    for run in list(runtime.runs.values()):
        if not run.done.done():
            await runtime.interrupt_run(run)
    try:
        envelope = repository.rollback_to(snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"snapshot {snapshot_id} not found") from exc
    return _workspace_config_payload(envelope, get_settings())


from app.api.chat_routes import router as chat_router
from app.api.chatgpt_routes import router as chatgpt_router, providers_router

router.include_router(chat_router)
router.include_router(chatgpt_router)
router.include_router(providers_router)
