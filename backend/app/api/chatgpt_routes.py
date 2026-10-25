from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from fastapi.responses import HTMLResponse

from app.agent.chatgpt_auth import CALLBACK_PATH, ChatGPTError
from app.api.deps import get_agent_runtime
from app.core.config import Settings, get_settings
from app.agent.codex_cli import CodexCLIClient

router = APIRouter(prefix="/api/v1/chatgpt")
callback_router = APIRouter()
providers_router = APIRouter(prefix="/api/v1/agent")


class APIKeyUpdate(BaseModel):
    key: str = Field(min_length=1, max_length=4096)


@providers_router.get("/openai-key")
def openai_key_status(runtime=Depends(get_agent_runtime)) -> dict:
    return runtime.api_key_status()


@providers_router.put("/openai-key")
async def openai_key_save(payload: APIKeyUpdate, runtime=Depends(get_agent_runtime)) -> dict:
    try:
        return await runtime.save_api_key(payload.key)
    except ChatGPTError as exc:
        raise HTTPException(status_code=422 if exc.code == "api_key_invalid" else 503, detail=str(exc)) from exc


@providers_router.delete("/openai-key")
def openai_key_delete(runtime=Depends(get_agent_runtime)) -> dict:
    try:
        return runtime.delete_api_key()
    except ChatGPTError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@providers_router.get("/models")
async def provider_models(runtime=Depends(get_agent_runtime)) -> dict:
    try:
        return {"provider": runtime.repository.current().workspace.config.agent_backend,
                "models": await runtime.models()}
    except ChatGPTError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@providers_router.get("/codex-status")
async def codex_status(runtime=Depends(get_agent_runtime)) -> dict:
    return await runtime.codex_cli.status()


@providers_router.get("/ruflo/status")
async def ruflo_status(runtime=Depends(get_agent_runtime)) -> dict:
    config = runtime.repository.current().workspace.config
    return await runtime.ruflo.status(config.agent_backend == "ruflo_native" or config.ruflo_enabled)


@router.get("/account")
async def account(runtime=Depends(get_agent_runtime)) -> dict:
    return await runtime.account()


@router.post("/login")
async def login(runtime=Depends(get_agent_runtime)) -> dict:
    try:
        return await runtime.start_login()
    except ChatGPTError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/login/cancel")
async def cancel_login(runtime=Depends(get_agent_runtime)) -> dict:
    runtime.auth.cancel_login()
    return {"ok": True}


@router.post("/logout")
async def logout(runtime=Depends(get_agent_runtime)) -> dict:
    try:
        warning = await runtime.logout()
    except ChatGPTError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "warning": warning}


def _page(title: str, body: str, status: int) -> HTMLResponse:
    html = (f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{escape(title)}</title>'
            '<style>body{font:17px system-ui;max-width:32rem;margin:18vh auto;padding:24px;color:#202123}h1{font-size:26px}</style>'
            f"<h1>{escape(title)}</h1><p>{escape(body)}</p></html>")
    return HTMLResponse(html, status_code=status, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"})


@callback_router.get(CALLBACK_PATH, include_in_schema=False)
async def oauth_callback(request: Request, settings: Settings = Depends(get_settings), runtime=Depends(get_agent_runtime)) -> HTMLResponse:
    # The registered redirect is the loopback address; reject other hosts reaching this route.
    if request.headers.get("host") != f"127.0.0.1:{settings.api_port}":
        return _page("Not found", "This address only completes a local Jew sign-in.", 404)
    try:
        await runtime.auth.complete_login(parse_qs(request.url.query, keep_blank_values=True))
    except ChatGPTError as exc:
        return _page("Sign-in did not finish", str(exc), 400)
    except Exception:
        # Fail closed without leaking credentials, codes or stack traces into the browser.
        return _page("Sign-in did not finish", "Jew could not save the connection. Return to Jew and try again.", 503)
    return _page("Return to Jew", "Jew is connected to your ChatGPT account. You can close this tab.", 200)
