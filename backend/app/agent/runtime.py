from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import logging
from dataclasses import dataclass, field
from threading import Lock
from uuid import uuid4

from app.agent.chatgpt_api import ChatGPTClient
from app.agent.chatgpt_auth import CALLBACK_PATH, ChatGPTAuth, ChatGPTError, KeyringCredentialStore
from app.agent.windows_credentials import WindowsCredentialStore, WindowsAPIKeyStore
from app.agent.providers import OllamaClient, OpenAIAPIClient
from app.agent.codex_cli import CodexCLIClient
from app.agent.ruflo_mcp import RufloMCP, specs as ruflo_specs
from app.agent.ruflo_native import execute_native_command
from app.agent.context import BASE_INSTRUCTIONS, developer_instructions, turn_context
from app.agent.contracts import CLOSURE_QUIZ_TOOLS, tool_specs
from app.agent.store import AgentStore
from app.core.config import Settings
from app.models.domain import ChatMessage, GraphChatRequest, TopicQuizSession
from app.services.repository import GraphRepository
from app.services.roadmap_studio import RoadmapGenerateRequest, RoadmapPreview, generate_roadmap_preview

ACTIVE = {"starting", "running", "waiting"}
# Bounds one learner turn; each step is one Responses call plus its tool results.
MAX_STEPS = 24
logger = logging.getLogger(__name__)


def agent_error(message: str) -> ChatGPTError:
    return ChatGPTError("agent_error", message)


@dataclass
class AgentRun:
    id: str
    graph_id: str
    session_id: str | None
    request: GraphChatRequest
    model: str
    done: asyncio.Future
    provider: str = ""
    status: str = "starting"
    error: str | None = None
    task: asyncio.Task | None = None
    messages: dict[str, ChatMessage] = field(default_factory=dict)
    tool_locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    interactions: dict[str, asyncio.Future] = field(default_factory=dict)
    quiz_topic_id: str | None = None
    quiz_count: int | None = None
    quiz_session: TopicQuizSession | None = None
    cancel_requested: bool = False
    web_searched: bool = False

    @property
    def thread_key(self) -> str:
        # Tool results are idempotent per conversation (or per one-off quiz run).
        return self.session_id or self.id


class AgentRuntime:
    """Jew's graph agent with interchangeable ChatGPT, local and API backends."""

    def __init__(self, settings: Settings, repository: GraphRepository, auth: ChatGPTAuth | None = None,
                 client: ChatGPTClient | None = None):
        self.settings = settings
        self.repository = repository
        self.store = AgentStore(repository)
        self.store.recover_interrupted()
        credential_account = ("desktop-" + hashlib.sha256(str(settings.db_path.resolve()).encode("utf-8")).hexdigest()[:32]
                              if settings.desktop_token else "connection")
        secure_store = (WindowsCredentialStore(settings.db_path.parent / f"chatgpt-{credential_account}.dpapi",
                                              KeyringCredentialStore(credential_account)) if sys.platform == "win32"
                        else KeyringCredentialStore(credential_account))
        self.auth = auth or ChatGPTAuth(redirect_uri=f"http://127.0.0.1:{settings.api_port}{CALLBACK_PATH}",
                                        registration_path=settings.db_path.parent / "chatgpt-registration.json",
                                        store=secure_store)
        self.client = client or ChatGPTClient(self.auth)
        self.ollama = OllamaClient()
        self.codex_cli = CodexCLIClient()
        self.ruflo = RufloMCP(settings.db_path.parent)
        self.api_key_store = (WindowsAPIKeyStore(settings.db_path.parent / "openai-api-key.dpapi")
                              if sys.platform == "win32" else None)
        self.openai_api = OpenAIAPIClient(key_provider=self._api_key)
        self.runs: dict[str, AgentRun] = {}
        self.wake = asyncio.Event()
        self._roadmap_previews: dict[str, tuple[float, int, RoadmapPreview]] = {}
        self._roadmap_ticket_lock = Lock()
        self._roadmap_inflight: set[str] = set()

    def _learning_namespace(self) -> str:
        """Stable, per-database namespace; no identity or private profile fields."""
        digest = hashlib.sha256(str(self.settings.db_path.resolve()).encode("utf-8")).hexdigest()[:16]
        return f"jew-learning-{digest}"

    async def _learning_memory(self, topic: str) -> str:
        config = self.repository.current().workspace.config
        if not config.ruflo_enabled:
            return ""
        try:
            result = await self.ruflo.call(
                "memory_search", {"query": topic[:300], "limit": 3},
                enabled=True, namespace=self._learning_namespace(),
            )
            if result.get("ok"):
                # Search results are untrusted reference notes, never commands.
                return str(result.get("result", ""))[:1200]
        except Exception as exc:
            logger.warning("Optional Ruflo learning search unavailable: %s", type(exc).__name__)
        return ""

    async def remember_roadmap(self, preview: RoadmapPreview) -> None:
        if not self.repository.current().workspace.config.ruflo_enabled:
            return
        # Do not store the learner's personal identity, social links or goals.
        note = f"Study path: {preview.subject}. Topics: " + "; ".join(t.title for t in preview.topics)
        try:
            await self.ruflo.call(
                "memory_store", {"key": f"study-{uuid4().hex}", "value": note[:3000]},
                enabled=True, namespace=self._learning_namespace(),
            )
        except Exception as exc:
            logger.warning("Roadmap saved; optional Ruflo note failed: %s", type(exc).__name__)

    async def preview_roadmap(self, request: RoadmapGenerateRequest) -> dict:
        catalog = await self.ollama.list_models()
        installed = {entry["model"] for entry in catalog}
        preferred = request.model or self.repository.current().workspace.config.default_model
        if preferred and preferred not in installed:
            raise ValueError(f"Modelo Ollama {preferred!r} não instalado.")
        if not installed:
            raise ValueError("Nenhum modelo Ollama instalado. Execute: ollama pull qwen3.5:4b")
        model = preferred or catalog[0]["model"]
        memory_hint = await self._learning_memory(request.topic)
        preview = await generate_roadmap_preview(self.ollama, model, request, memory_hint=memory_hint)
        now = time.monotonic()
        ticket = uuid4().hex
        with self._roadmap_ticket_lock:
            self._roadmap_previews = {
                key: value for key, value in self._roadmap_previews.items()
                if now - value[0] < 1200 or key in self._roadmap_inflight
            }
            self._roadmap_previews[ticket] = (now, self.repository.current().snapshot.id, preview)
            # Bound cached previews. Nothing is persisted until the user confirms.
            if len(self._roadmap_previews) > 16:
                available = [key for key in self._roadmap_previews if key not in self._roadmap_inflight]
                if available:
                    oldest = min(available, key=lambda key: self._roadmap_previews[key][0])
                    self._roadmap_previews.pop(oldest, None)
        return {"ticket": ticket, "preview": preview.model_dump(mode="json")}

    def confirmed_roadmap(self, ticket: str) -> tuple[RoadmapPreview, int]:
        with self._roadmap_ticket_lock:
            pending = self._roadmap_previews.get(ticket)
            if pending is None or time.monotonic() - pending[0] > 1200:
                raise ValueError("Prévia expirada. Gere um novo roadmap.")
            if ticket in self._roadmap_inflight:
                raise ValueError("Esta prévia já está sendo confirmada.")
            self._roadmap_inflight.add(ticket)
            return pending[2], pending[1]

    def release_roadmap_preview(self, ticket: str) -> None:
        with self._roadmap_ticket_lock:
            self._roadmap_inflight.discard(ticket)

    def discard_roadmap_preview(self, ticket: str) -> None:
        with self._roadmap_ticket_lock:
            self._roadmap_previews.pop(ticket, None)
            self._roadmap_inflight.discard(ticket)

    def _api_key(self) -> str | None:
        if self.api_key_store:
            saved = self.api_key_store.read()
            if saved:
                return saved
        return os.environ.get("OPENAI_API_KEY")

    def api_key_status(self) -> dict:
        stored = self.api_key_store is not None and self.api_key_store.path.exists()
        return {"configured": stored or bool(os.environ.get("OPENAI_API_KEY")),
                "source": "windows" if stored else "environment" if os.environ.get("OPENAI_API_KEY") else None,
                "editable": self.api_key_store is not None}

    async def save_api_key(self, key: str) -> dict:
        if self.api_key_store is None:
            raise ChatGPTError("storage_unavailable", "Secure key management requires Windows. Use OPENAI_API_KEY on this platform.")
        if not key.strip() or len(key) > 4096 or "\n" in key or "\r" in key:
            raise ChatGPTError("api_key_invalid", "Enter a valid OpenAI API key.")
        # Test before persisting. Existing credentials are not lost on a failed attempt.
        await self.openai_api.list_models(key.strip())
        self.api_key_store.write(key.strip())
        return self.api_key_status()

    def delete_api_key(self) -> dict:
        if self.api_key_store is None:
            raise ChatGPTError("storage_unavailable", "No saved Windows API key is available.")
        self.api_key_store.delete()
        return self.api_key_status()

    # Account

    def _active(self) -> bool:
        return any(run.status in ACTIVE for run in self.runs.values())

    async def models(self, provider: str | None = None) -> list[dict]:
        provider = provider or self.repository.current().workspace.config.agent_backend

        if provider in {"ruflo_native", "ollama"}:
            return await self.ollama.list_models()
        if provider == "openai_api":
            return await self.openai_api.list_models()
        if provider == "codex_cli":
            return await self.codex_cli.list_models()
        return [{"id": m["slug"], "model": m["slug"], "displayName": m["display_name"],
                 "description": m.get("description") or "", "isDefault": index == 0}
                for index, m in enumerate(await self.client.list_models())]

    async def account(self) -> dict:
        status = self.auth.status()
        login = self.auth.pending or self.auth.completing
        result = {"connected": True, **status, "models": [],
                  "login": {"loginId": login.login_id, "authUrl": login.auth_url,
                            "phase": "completing" if self.auth.completing is login else "pending"} if login else None}
        if status["authenticated"] and status["sharing"]:
            try:
                # The account screen always shows ChatGPT models, regardless of
                # the workspace's active provider.
                result["models"] = [{"id": m["slug"], "model": m["slug"], "displayName": m["display_name"],
                                     "description": m.get("description") or "", "isDefault": index == 0}
                                    for index, m in enumerate(await self.client.list_models())]
            except ChatGPTError as exc:
                result.update(self.auth.status())
                result["error"] = str(exc)
            else:
                result.update(self.auth.status())
                if not result["authenticated"] or not result["sharing"]:
                    result["models"] = []
        return result

    async def start_login(self) -> dict:
        if self._active():
            raise agent_error("Stop active conversations before changing the ChatGPT account.")
        login = await self.auth.start_login()
        return {"loginId": login.login_id, "authUrl": login.auth_url,
                "phase": "completing" if self.auth.completing is login else "pending"}

    async def logout(self) -> str | None:
        if self._active():
            raise agent_error("Stop active conversations before signing out.")
        return await self.auth.logout()

    async def _select_model(self, requested: str | None, provider: str | None = None) -> str:
        provider = provider or self.repository.current().workspace.config.agent_backend

        models = await self.models(provider)
        selected = requested or self.repository.current().workspace.config.default_model
        if selected is None:
            if not models:
                if provider in {"ollama", "ruflo_native"}:
                    raise agent_error("Nenhum modelo Ollama instalado. No CMD execute: ollama pull qwen3.5:4b (ou instale outro modelo compatível). Abra o Ollama e atualize os modelos nas Configurações.")
                raise agent_error(f"No models available for {provider}. Install or configure a model in settings.")
            return models[0]["model"]
        if not any(model["model"] == selected for model in models):
            raise agent_error(f"The selected {provider} model is unavailable: {selected}. Choose another model.")
        return selected

    # Turns

    async def start_chat(self, graph_id: str, request: GraphChatRequest) -> tuple[str, str]:
        graph = self.repository.graph(graph_id)
        thread = self.repository.chat_thread(graph_id, request.session_id)
        selected_topic = request.selected_topic_id or thread.topic_id
        if selected_topic and not any(t.id == selected_topic for t in graph.topics):
            raise ValueError("The selected topic does not belong to this graph.")
        client_id = request.client_message_id or f"user-{uuid4().hex}"
        binding = self.store.binding(thread.session_id)
        if binding.get("client_message_id") == client_id and binding.get("run_id"):
            original = next((m for m in thread.messages if m.id == client_id), None)
            if original is None or original.content != request.prompt or original.hidden != request.hidden_user_message:
                raise ValueError("Conflicting client message id.")
            return thread.session_id, binding["run_id"]
        with self.repository._connect() as conn:
            if conn.execute("SELECT 1 FROM chat_messages WHERE message_id=?", (client_id,)).fetchone():
                raise ValueError("This client message id has already been used.")
        run = AgentRun(id=uuid4().hex, graph_id=graph_id, session_id=thread.session_id,
                       request=request.model_copy(update={"selected_topic_id": selected_topic, "session_id": thread.session_id}),
                       model=request.model or "", done=asyncio.get_running_loop().create_future(),
                       provider=self.repository.current().workspace.config.agent_backend)
        self.store.begin(thread.session_id, run.id, client_id)
        self.store.put_message(graph_id, thread.session_id, ChatMessage(id=client_id, role="user", content=request.prompt, hidden=request.hidden_user_message))
        self.runs[run.id] = run
        self.emit(run, {"type": "thread_state", "thread": self.store.thread_payload(graph_id, thread.session_id)})
        run.task = asyncio.create_task(self._execute(run, thread.messages))
        return thread.session_id, run.id

    async def generate_closure_quiz(self, graph_id: str, topic_id: str, question_count: int, model: str | None) -> TopicQuizSession:
        from app.services.quiz_service import QuizService
        graph = self.repository.graph(graph_id)
        closure = QuizService(self.settings).build_closure_status(graph, topic_id)
        if not closure.can_award_completion:
            raise ValueError("Close prerequisite topics before taking this completion test.")
        provider = self.repository.current().workspace.config.agent_backend
        selected = await self._select_model(model, provider)
        run = AgentRun(id=uuid4().hex, graph_id=graph_id, session_id=None, model=selected,
                       provider=provider,
                       request=GraphChatRequest(prompt=f"Prepare a closure quiz for topic {topic_id}: exactly {question_count} questions. Call create_closure_quiz with the questions.", selected_topic_id=topic_id),
                       done=asyncio.get_running_loop().create_future(), quiz_topic_id=topic_id, quiz_count=question_count)
        self.runs[run.id] = run
        run.task = asyncio.create_task(self._execute(run, []))
        try:
            await asyncio.shield(run.done)
            if run.error:
                raise agent_error(run.error)
            if run.quiz_session is None:
                raise agent_error("The model finished without creating the requested quiz.")
            return run.quiz_session
        finally:
            if not run.done.done():
                await self.interrupt_run(run)
            self.runs.pop(run.id, None)

    async def generate_lesson(self, graph_id: str, topic_id: str, model: str | None = None):
        """Generate, version and persist a lesson with an installed Ollama model."""
        from app.models.domain import Artifact

        graph = self.repository.graph(graph_id)
        topic = next((item for item in graph.topics if item.id == topic_id), None)
        if topic is None:
            raise KeyError(topic_id)
        catalog = await self.ollama.list_models()
        installed = {entry["model"] for entry in catalog}
        if not installed:
            raise ValueError("No Ollama model installed. Run: ollama pull qwen3.5:4b")
        configured = self.repository.current().workspace.config.default_model
        selected = model or (configured if configured in installed else catalog[0]["model"])
        if selected not in installed:
            raise ValueError(f"Ollama model {selected!r} is not installed. Select an installed local model.")

        prerequisite_ids = {edge.source_topic_id for edge in graph.edges
                            if edge.target_topic_id == topic_id and edge.relation == "requires"}
        context = {
            "subject": graph.subject, "graph_language": graph.language,
            "topic": {"id": topic.id, "title": topic.title, "description": topic.description[:4000],
                      "difficulty": topic.difficulty, "estimated_minutes": topic.estimated_minutes},
            "prerequisites": [{"title": item.title, "description": item.description[:500]}
                              for item in graph.topics if item.id in prerequisite_ids],
        }
        draft = await self.ollama.generate_lesson(selected, context)
        sections = [
            "## Objetivos de aprendizagem\n" + "\n".join(f"- {item}" for item in draft.objectives),
            "## Explicação\n" + draft.explanation,
            "## Exemplos resolvidos\n" + "\n\n".join(f"{index}. {item}" for index, item in enumerate(draft.examples, 1)),
            "## Pratique\n" + "\n\n".join(f"{index}. {item}" for index, item in enumerate(draft.practice, 1)),
            "## Resumo\n" + draft.summary,
        ]
        artifact = Artifact(id=f"lesson-{uuid4().hex}", title=draft.title, kind="lesson", body="\n\n".join(sections))
        # Each generation is a new artifact/snapshot; previous lessons and quiz attempts survive.
        workspace = self.repository.append_topic_artifact(graph_id, topic_id, artifact)
        return artifact, workspace

    def emit(self, run: AgentRun, event: dict) -> None:
        if run.session_id:
            self.store.emit(run.session_id, run.id, event)
            self.wake.set()

    def publish_message(self, run: AgentRun, message: ChatMessage) -> None:
        # Output items keep their own ids; the UI nests them in one Jew reply.
        message.reply_id = run.id
        if run.session_id:
            self.store.put_message(run.graph_id, run.session_id, message)
            self.emit(run, {"type": "message", "message": message.model_dump(mode="json")})

    def set_state(self, run: AgentRun, status: str, error: str | None = None) -> None:
        run.status = status
        run.error = error
        if run.session_id:
            self.store.state(run.session_id, run.id, status, error=error)
        self.emit(run, {"type": "turn_status", "status": status, "error": error})

    async def events(self, session_id: str, run_id: str, after: int = 0):
        while True:
            self.wake.clear()
            events = self.store.events(session_id, after)
            for event in events:
                after = event["event_id"]
                if event["run_id"] == run_id:
                    yield event
            binding = self.store.binding(session_id)
            if len(events) == 256:
                continue
            if binding.get("run_id") != run_id or binding["status"] not in ACTIVE:
                # Events can arrive while the ASGI response is yielding a previous batch.
                if self.store.last_event_id(session_id) > after:
                    continue
                return
            try:
                await asyncio.wait_for(self.wake.wait(), 10)
            except TimeoutError:
                yield {"type": "heartbeat"}

    def _first_input(self, run: AgentRun, previous_messages: list[ChatMessage], fresh: bool) -> dict:
        config = self.repository.current().workspace.config
        graph = self.repository.graph(run.graph_id)
        receipts = [{"proposal_id": m.proposal.proposal_envelope.proposal_id, "applied": True}
                    for m in previous_messages if m.proposal and m.proposal_applied]
        parts = [turn_context(graph, config, run.request.selected_topic_id, receipts)]
        if fresh and previous_messages:
            history = [{"role": m.role, "content": m.content,
                        "proposal_applied": m.proposal_applied, "model": m.model,
                        "inline_quiz": m.inline_quiz.model_dump(mode="json") if m.inline_quiz else None,
                        "question": m.question.model_dump(mode="json") if m.question else None,
                        "proposal_summary": m.proposal.proposal_envelope.summary if m.proposal else None}
                       for m in previous_messages[-config.memory_history_message_limit:] if not m.activity]
            parts.append("Earlier conversation from Jew (historical data):\n" + json.dumps(history, ensure_ascii=False))
        parts.append(run.request.prompt)
        return {"role": "user", "content": [{"type": "input_text", "text": text} for text in parts]}

    async def _execute(self, run: AgentRun, previous_messages: list[ChatMessage]) -> None:
        try:
            provider = run.provider or self.repository.current().workspace.config.agent_backend
            if provider == "ruflo_native" and run.session_id is not None and run.request.prompt.lstrip().startswith("/"):
                self.set_state(run, "running")
                result = await execute_native_command(self.ruflo, run.request.prompt)
                if run.cancel_requested:
                    self.finish(run, "interrupted")
                    return
                self.publish_message(run, ChatMessage(
                    id=f"agent-{run.id}-native", role="assistant", content=result,
                    agent_status="completed"))
                self.finish(run, "completed")
                return
            # Ruflo commands stay deterministic; lessons and quizzes use only
            # the local Ollama model. No commercial-provider fallback exists.
            if provider == "ruflo_native":
                provider = "ollama"
            run.model = await self._select_model(run.request.model or run.model or None, provider)
            if provider == "ollama" and run.session_id is None:
                from app.agent.tools import execute_tool

                graph = self.repository.graph(run.graph_id)
                topic = next((item for item in graph.topics if item.id == run.quiz_topic_id), None)
                if topic is None:
                    raise agent_error("Quiz topic not found.")
                self.set_state(run, "running")
                draft = await self.ollama.generate_quiz(run.model, topic.model_dump(mode="json"), run.quiz_count or 6)
                result = await execute_tool(self, run, "create_closure_quiz", f"local-{uuid4().hex}",
                                            draft.model_dump_json())
                if run.quiz_session is None:
                    raise agent_error(f"The local model produced a quiz that Jew could not save: {result}")
                self.finish(run, "completed")
                return
            config = self.repository.current().workspace.config
            tools = tool_specs(CLOSURE_QUIZ_TOOLS if run.session_id is None else None)
            if run.session_id is not None and config.ruflo_enabled:
                tools.extend(ruflo_specs())
            # Chat turns may search the web; the model decides when. Quiz generation stays offline.
            if run.session_id is not None and provider in {"chatgpt", "openai_api"}:
                tools.append({"type": "web_search"})
            transcript = self.store.transcript(run.session_id) if run.session_id else None
            items = list(transcript or [])
            items.append(self._first_input(run, previous_messages, fresh=transcript is None))
            payload = {"model": run.model, "instructions": BASE_INSTRUCTIONS + "\n" + developer_instructions(config),
                       "tools": tools, "parallel_tool_calls": False,
                       **({"include": ["reasoning.encrypted_content"]} if provider == "chatgpt" else {}),
                       **({"reasoning": {"effort": config.reasoning_effort}} if config.reasoning_effort and provider != "ollama" else {})}
            client = {"chatgpt": self.client, "ollama": self.ollama, "openai_api": self.openai_api,
                      "codex_cli": self.codex_cli}[provider]
            self.set_state(run, "running")
            for _ in range(MAX_STEPS):
                response = await client.stream({**payload, "input": items}, lambda event: self._stream_event(run, event))
                output = [item for item in response.get("output", []) if isinstance(item, dict)]
                for item in output:
                    if item.get("type") == "message":
                        self._message_done(run, item)
                    elif item.get("type") == "web_search_call":
                        run.web_searched = True
                items.extend(output)
                calls = [item for item in output if item.get("type") == "function_call"]
                if not calls:
                    self._save_transcript(run, items)
                    self.finish(run, "completed")
                    return
                from app.agent.tools import execute_tool
                for call in calls:
                    lock = run.tool_locks.setdefault(call["call_id"], asyncio.Lock())
                    async with lock:
                        output_text = await execute_tool(self, run, call["name"], call["call_id"], call.get("arguments") or "")
                    items.append({"type": "function_call_output", "call_id": call["call_id"], "output": output_text})
                self._save_transcript(run, items)
                if run.cancel_requested:
                    self.finish(run, "interrupted")
                    return
            raise agent_error(f"The model did not finish within {MAX_STEPS} steps. Continue the conversation to resume.")
        except asyncio.CancelledError:
            self.finish(run, "interrupted")
        except Exception as exc:
            self.finish(run, "failed", str(exc))

    def _save_transcript(self, run: AgentRun, items: list[dict]) -> None:
        if run.session_id:
            self.store.save_transcript(run.session_id, items)

    def _assistant_message(self, run: AgentRun, item_id: str) -> ChatMessage:
        message = run.messages.get(item_id)
        if message is None:
            message = ChatMessage(id=f"agent-{run.id}-{item_id}", role="assistant", content="", model=run.model, agent_status="streaming")
            run.messages[item_id] = message
        return message

    async def _stream_event(self, run: AgentRun, event: dict) -> None:
        kind = event.get("type")
        if kind == "response.output_text.delta" and isinstance(event.get("delta"), str):
            message = self._assistant_message(run, str(event.get("item_id")))
            message.content += event["delta"]
            self.publish_message(run, message)
        elif kind == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") == "message":
                message = self._assistant_message(run, str(item.get("id")))
                if item.get("phase") in {"commentary", "final_answer"}:
                    message.message_phase = item["phase"]
                self.publish_message(run, message)

    def _message_done(self, run: AgentRun, item: dict) -> None:
        message = self._assistant_message(run, str(item.get("id")))
        text = "".join(part.get("text", "") for part in item.get("content", [])
                       if isinstance(part, dict) and part.get("type") == "output_text")
        message.content = text or message.content
        if item.get("phase") in {"commentary", "final_answer"}:
            message.message_phase = item["phase"]
        message.agent_status = "completed"
        self.publish_message(run, message)

    async def answer(self, graph_id: str, session_id: str, interaction_id: str, *, answer: str | None, choice_index: int | None) -> dict:
        thread = self.repository.chat_thread(graph_id, session_id)
        run = next((r for r in self.runs.values() if r.session_id == thread.session_id and interaction_id in r.interactions and not r.done.done()), None)
        if run is None:
            raise ValueError("This question is no longer waiting for an answer. Continue the conversation.")
        future = run.interactions[interaction_id]
        if future.done():
            raise ValueError("This question was already answered.")
        message = next((m for m in thread.messages if (m.question and m.question.interaction_id == interaction_id) or (m.inline_quiz and m.inline_quiz.interaction_id == interaction_id)), None)
        if message is None:
            raise ValueError("Question not found in this conversation.")
        if message.inline_quiz:
            quiz = message.inline_quiz
            if choice_index is None or not 0 <= choice_index < len(quiz.choices):
                raise ValueError("Choose one answer.")
            quiz.answered_index = choice_index
            quiz.status = "answered"
            result = {"question": quiz.question, "selected_answer": quiz.choices[choice_index],
                      "correct": choice_index == quiz.correct_index, "correct_answer": quiz.choices[quiz.correct_index]}
        else:
            question = message.question
            assert question is not None
            if choice_index is not None:
                if not 0 <= choice_index < len(question.choices):
                    raise ValueError("Invalid answer choice.")
                answer = question.choices[choice_index]
            if not answer or not answer.strip():
                raise ValueError("Enter an answer.")
            question.answer = answer.strip()
            question.status = "answered"
            result = {"question": question.question, "answer": question.answer}
        self.publish_message(run, message)
        self.set_state(run, "waiting" if sum(not item.done() for item in run.interactions.values()) > 1 else "running")
        future.set_result(result)
        return {"ok": True, "message": message.model_dump(mode="json")}

    async def interrupt(self, graph_id: str, session_id: str) -> None:
        thread = self.repository.chat_thread(graph_id, session_id)
        run = next((r for r in self.runs.values() if r.session_id == thread.session_id and not r.done.done()), None)
        if run is not None:
            await self.interrupt_run(run)

    async def interrupt_run(self, run: AgentRun) -> None:
        run.cancel_requested = True
        for future in run.interactions.values():
            if not future.done():
                future.set_exception(agent_error("The user stopped this turn."))
        if run.task and run.task is not asyncio.current_task() and not run.task.done():
            run.task.cancel()
            await asyncio.gather(run.task, return_exceptions=True)
        self.finish(run, "interrupted")

    def finish(self, run: AgentRun, status: str, error: str | None = None) -> None:
        if run.done.done():
            return
        status = status if status in {"completed", "interrupted", "failed"} else "failed"
        for future in run.interactions.values():
            if not future.done():
                future.set_exception(agent_error(error or "The turn ended."))
        if run.session_id:
            thread = self.repository.chat_thread(run.graph_id, run.session_id)
            for message in thread.messages:
                changed = False
                if message.agent_status == "streaming":
                    message.agent_status = status
                    changed = True
                if message.activity and message.activity.status == "running":
                    message.activity.status = "failed"
                    message.activity.detail = error or "The turn ended before this tool completed."
                    changed = True
                for widget in (message.question, message.inline_quiz):
                    if widget and widget.status == "pending":
                        widget.status = "interrupted"
                        changed = True
                if changed:
                    self.publish_message(run, message)
        self.set_state(run, status, error)
        self.emit(run, {"type": "turn_completed", "status": status, "error": error})
        run.done.set_result(None)
        self.runs.pop(run.id, None)

    async def close(self) -> None:
        with self._roadmap_ticket_lock:
            self._roadmap_previews.clear()
            self._roadmap_inflight.clear()
        for run in list(self.runs.values()):
            if not run.done.done():
                await self.interrupt_run(run)
        await self.auth.close()
        await self.ollama.close()
        await self.openai_api.close()
        await self.codex_cli.close()
        await self.ruflo.close()
