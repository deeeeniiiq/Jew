"""Opt-in Ruflo MCP tools for Jew. Ruflo never selects or runs an AI model here."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Literal

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel, ConfigDict, Field


VERSION = "3.59.17"
PREFIX = "ruflo_"


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SwarmInit(Arguments):
    topology: Literal["hierarchical", "mesh", "hierarchical-mesh", "ring", "star", "hybrid", "adaptive"] = "hierarchical"
    maxAgents: int = Field(default=3, ge=1, le=10)
    strategy: Literal["specialized", "balanced", "adaptive"] = "balanced"


class SwarmStatus(Arguments):
    swarmId: str | None = Field(default=None, max_length=150)


class AgentList(Arguments):
    status: str | None = Field(default=None, max_length=50)


class MemorySearch(Arguments):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class MemoryStore(Arguments):
    key: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=4000)


# Only explicit, constrained tools are bridged to the model. In particular,
# agent_spawn's model aliases are Claude models; spawning one would violate
# the user-selected Codex-only inference path.
MODELS: dict[str, type[Arguments]] = {
    "swarm_init": SwarmInit,
    "swarm_status": SwarmStatus,
    "agent_list": AgentList,
    "memory_search": MemorySearch,
    "memory_store": MemoryStore,
}
DESCRIPTIONS = {
    "swarm_init": "Initialize Ruflo swarm metadata. This does not run an AI model or spawn agents.",
    "swarm_status": "Read Ruflo swarm status.",
    "agent_list": "List Ruflo agent registrations; never start a model.",
    "memory_search": "Search Ruflo memory entries in Jew's isolated namespace.",
    "memory_store": "Store a short memory note in Jew's Ruflo namespace. Does not change the Jew graph.",
}


def specs() -> list[dict[str, Any]]:
    return [{"type": "function", "name": PREFIX + name,
             "description": description, "parameters": MODELS[name].model_json_schema(), "strict": False}
            for name, description in DESCRIPTIONS.items()]


class RufloMCP:
    """Lazy MCP worker. The task that opens the AnyIO session also closes it."""

    def __init__(self, directory: Path):
        self.directory = directory / "ruflo"
        self._lock = asyncio.Lock()
        self._worker: asyncio.Task[None] | None = None
        self._ready: asyncio.Future[None] | None = None
        self._queue: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]]] | None = None

    @staticmethod
    def _environment() -> dict[str, str]:
        allowed = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
                   "TEMP", "TMP", "PROGRAMFILES", "PROGRAMFILES(X86)", "HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"}
        return {k: v for k, v in os.environ.items() if k.upper() in allowed}

    @staticmethod
    def _launcher() -> tuple[str, list[str]]:
        # Prefer the documented global installation. Existing npx caches remain
        # supported for development; --no-install never downloads a package.
        global_command = "ruflo.cmd" if sys.platform == "win32" else "ruflo"
        if shutil.which(global_command):
            return global_command, []
        npx = "npx.cmd" if sys.platform == "win32" else "npx"
        return npx, ["--no-install", f"ruflo@{VERSION}"]

    def _parameters(self) -> StdioServerParameters:
        # No ChatGPT/Codex credential paths or model-provider API keys are sent to Ruflo.
        launcher, bootstrap = self._launcher()
        if sys.platform == "win32":
            return StdioServerParameters(command="cmd.exe", args=["/d", "/s", "/c",
                " ".join([launcher, *bootstrap, "mcp", "start"])], env=self._environment(), cwd=self.directory)
        return StdioServerParameters(command=launcher, args=[*bootstrap, "mcp", "start"],
                                     env=self._environment(), cwd=self.directory)

    async def _prepare_memory(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        db = self.directory / "memory.sqlite3"
        if db.is_file():
            return
        launcher, bootstrap = self._launcher()
        # Pass the database path as a separate argument to avoid breaking paths
        # with spaces when executing npm's Windows .cmd wrappers.
        args = [launcher, *bootstrap, "memory", "init", "--backend", "sqlite", "--path", str(db)]
        process = await asyncio.create_subprocess_exec(*args, cwd=str(self.directory), env=self._environment(),
                                                        stdout=asyncio.subprocess.DEVNULL,
                                                        stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.wait(), timeout=60)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode != 0 or not db.is_file():
            raise RuntimeError("Ruflo could not initialize Jew's isolated memory database.")

    async def _serve(self, ready: asyncio.Future[None],
                     queue: asyncio.Queue[tuple[str, dict[str, Any], asyncio.Future[Any]]]) -> None:
        current: asyncio.Future[Any] | None = None
        try:
            await self._prepare_memory()
            async with AsyncExitStack() as stack:
                reader, writer = await stack.enter_async_context(stdio_client(self._parameters()))
                session = await stack.enter_async_context(ClientSession(reader, writer))
                await asyncio.wait_for(session.initialize(), timeout=35)
                available = {tool.name for tool in (await asyncio.wait_for(session.list_tools(), timeout=15)).tools}
                if not set(MODELS).issubset(available):
                    raise RuntimeError("Installed Ruflo version does not expose the required MCP tools.")
                if not ready.done():
                    ready.set_result(None)
                while True:
                    name, arguments, current = await queue.get()
                    if current.cancelled():
                        current = None
                        continue
                    try:
                        result = await asyncio.wait_for(session.call_tool(name, arguments), timeout=35)
                    except TimeoutError:
                        raise RuntimeError("Ruflo MCP stopped responding; restart the connection.")
                    if not current.done():
                        current.set_result(result)
                    current = None
        except BaseException as exc:
            if not ready.done():
                if isinstance(exc, asyncio.CancelledError):
                    ready.cancel()
                else:
                    ready.set_exception(exc)
            if current is not None and not current.done():
                current.set_exception(RuntimeError("Ruflo MCP connection ended."))
            while not queue.empty():
                _, _, waiting = queue.get_nowait()
                if not waiting.done():
                    waiting.set_exception(RuntimeError("Ruflo MCP connection ended."))
            if not isinstance(exc, asyncio.CancelledError):
                raise

    async def _ensure(self) -> None:
        async with self._lock:
            if self._worker is None or self._worker.done():
                loop = asyncio.get_running_loop()
                self._ready = loop.create_future()
                self._queue = asyncio.Queue(maxsize=32)
                self._worker = asyncio.create_task(self._serve(self._ready, self._queue))
            ready = self._ready
        assert ready is not None
        await asyncio.wait_for(asyncio.shield(ready), timeout=55)

    async def status(self, enabled: bool) -> dict:
        if not enabled:
            await self.close()
            return {"enabled": False, "connected": False, "version": VERSION,
                    "message": "Enable Ruflo in Jew settings to use MCP tools."}
        try:
            await self._ensure()
        except Exception as exc:
            await self.close()
            return {"enabled": True, "connected": False, "version": VERSION,
                    "message": f"Ruflo MCP unavailable: {type(exc).__name__}. Install Ruflo {VERSION} locally using npm."}
        return {"enabled": True, "connected": True, "version": VERSION,
                "tools": [PREFIX + name for name in MODELS]}

    async def call(self, name: str, arguments: dict[str, Any], *, enabled: bool,
                   namespace: str = "jew") -> dict:
        if not enabled:
            raise ValueError("Enable Ruflo in Jew settings first.")
        if name not in MODELS:
            raise ValueError("This Ruflo operation is not allowed.")
        validated = MODELS[name].model_validate(arguments).model_dump(exclude_none=True)
        if name.startswith("memory_"):
            if namespace != "jew" and not re.fullmatch(r"jew-learning-[a-f0-9]{16}", namespace):
                raise ValueError("Invalid Ruflo learning namespace")
            validated["namespace"] = namespace
            validated["dbPath"] = str(self.directory / "memory.sqlite3")
        try:
            await self._ensure()
            loop = asyncio.get_running_loop()
            waiter = loop.create_future()
            async with self._lock:
                if self._worker is None or self._worker.done() or self._queue is None:
                    raise RuntimeError("Ruflo MCP disconnected.")
                self._queue.put_nowait((name, validated, waiter))
            result = await asyncio.wait_for(asyncio.shield(waiter), timeout=50)
        except (OSError, RuntimeError, TimeoutError, ExceptionGroup, asyncio.QueueFull) as exc:
            if isinstance(exc, TimeoutError):
                await self.close()
            raise RuntimeError(f"Ruflo MCP {name} failed ({type(exc).__name__}). Check Ruflo installation and logs.") from exc
        content = "\n".join(str(getattr(item, "text", "")) for item in result.content)
        return {"ok": not result.isError, "result": content[:12000], "truncated": len(content) > 12000}

    async def close(self) -> None:
        async with self._lock:
            worker = self._worker
            self._worker = None
            self._ready = None
            self._queue = None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
