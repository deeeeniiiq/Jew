"""Deterministic Jew commands backed exclusively by Ruflo MCP.

This module deliberately has no LLM client, model selection, or shell execution.
"""
from __future__ import annotations

import json
import shlex
from typing import Any

from app.agent.ruflo_mcp import RufloMCP


HELP = """**Ruflo nativo — sem GPT, login ou créditos de IA**

Comandos disponíveis:

`/help` — mostrar estes comandos
`/ruflo status` — verificar a conexão MCP
`/ruflo agents` — listar registros de agentes
`/ruflo swarm status [id]` — consultar o swarm
`/ruflo swarm init [hierarchical|mesh|ring|star|hybrid|adaptive]` — inicializar metadados do swarm
`/ruflo memory search <texto>` — procurar na memória local
`/ruflo memory store <chave> <texto>` — salvar uma nota na memória local

Os comandos acima usam apenas Ruflo. Perguntas comuns, aulas e quizzes usam um modelo Ollama
instalado localmente, sem créditos, login ou limites de uso do ChatGPT. Para configurar, instale
Ollama, execute `ollama pull qwen3.5:4b` no CMD (ou instale outro modelo compatível)
e selecione o modelo nas Configurações."""


def _pretty(value: Any) -> str:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return value
    return json.dumps(value, ensure_ascii=False, indent=2)


async def execute_native_command(ruflo: RufloMCP, prompt: str) -> str:
    """Dispatch a small allowlist. Never interpret the prompt as executable code."""
    try:
        parts = shlex.split(prompt.strip())
    except ValueError:
        return "Aspas incompletas. Use `/help` para ver os comandos."
    if not parts or parts[0].lower() in {"/help", "/ajuda"}:
        return HELP
    if parts[0].lower() != "/ruflo":
        return "O Ruflo nativo executa comandos explícitos; não gera respostas com IA. Digite `/help` para começar."

    command = [part.lower() for part in parts[:3]]
    name: str
    args: dict[str, Any]
    if len(parts) == 2 and command[1] == "status":
        status = await ruflo.status(True)
        return "**Estado do Ruflo MCP**\n\n```json\n" + _pretty(status) + "\n```"
    if len(parts) == 2 and command[1] == "agents":
        name, args = "agent_list", {}
    elif len(parts) >= 3 and command[1:3] == ["swarm", "status"] and len(parts) <= 4:
        name, args = "swarm_status", {"swarmId": parts[3]} if len(parts) == 4 else {}
    elif len(parts) >= 3 and command[1:3] == ["swarm", "init"] and len(parts) <= 4:
        name, args = "swarm_init", {"topology": parts[3]} if len(parts) == 4 else {}
    elif len(parts) >= 4 and command[1:3] == ["memory", "search"]:
        name, args = "memory_search", {"query": " ".join(parts[3:])}
    elif len(parts) >= 5 and command[1:3] == ["memory", "store"]:
        name, args = "memory_store", {"key": parts[3], "value": " ".join(parts[4:])}
    else:
        return "Comando desconhecido ou incompleto. Digite `/help` para ver os formatos aceitos."

    result = await ruflo.call(name, args, enabled=True)
    label = "Concluído" if result["ok"] else "Ruflo retornou um erro"
    return f"**{label}: {name}**\n\n```json\n{_pretty(result['result'])}\n```"
