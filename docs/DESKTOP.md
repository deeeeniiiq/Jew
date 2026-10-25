# JEW Desktop - instalacao, dados e verificacao

JEW 1.0.0 integra Electron, o frontend React e um backend Python embarcado. O backend atende somente em `127.0.0.1`, com porta escolhida a cada inicializacao. O esquema interno `clew://app` permanece por compatibilidade com perfis antigos. O encerramento do Electron aguarda o termino do processo Python antes de concluir a limpeza.

O modo padrao para novas instalacoes e **Ruflo + Ollama**. Aulas e explicacoes no chat e quizzes de conclusao usam inferencia local via Ollama, sem tokens de APIs comerciais. Ruflo oferece comandos e memoria MCP, mas nao gera texto sozinho. Consulte tambem o [README](../README.md).

## Install

Para o build local Windows deste projeto, o instalador fica em `desktop/artifacts/Jew-1.0.0-win-x64.exe` depois de executar `npm run package`. Um instalador existente nessa pasta pode estar desatualizado em relacao ao codigo-fonte atual; reconstrua e rode o smoke test apos alteracoes. Os [releases do Clew original](https://github.com/miuuyy/Clew/releases/latest) **nao sao releases JEW**.

- **Windows x64:** run the installer. Installation is per-user; WSL is not required.
- **macOS 13+:** o fluxo original de empacotamento oferece builds Intel e Apple Silicon; uma distribuicao macOS da marca JEW requer compilacao e validacao independentes antes de ser recomendada.
- **Linux:** choose x64 or arm64. Debian installation is system-wide; data remains per-user. AppImage requires FUSE 2 and working unprivileged user namespaces; make it executable and run it as your user. Use the Debian package on distributions that restrict AppImage namespaces. Linux also needs a desktop session with Secret Service and D-Bus for credential storage. CI baselines are Ubuntu 22.04 x64 and Ubuntu 24.04 arm64.

macOS builds are ad-hoc signed, without Apple Developer ID notarization. Windows builds are not Authenticode signed. The OS can show an unidentified-publisher warning. No release script disables platform protections.

O modo local **nao exige login ChatGPT**. Para gerar conteudo sem cotas comerciais, instale o [Ollama](https://ollama.com/download/windows), baixe um modelo (`ollama pull qwen3.5:4b` ou outro compativel), configure **Settings > Model provider > Ruflo + Ollama**, atualize a lista de modelos e selecione um modelo instalado. O modelo `qwen3.5:4b` foi usado na validacao local de explicacoes em 23/10/2026. CPU, RAM, memoria em disco e tempo de resposta continuam sendo limites fisicos.

Para recursos MCP, instale Node.js e Ruflo 3.59.17 (`npm install -g ruflo@3.59.17`); em seguida, use **Check connection** nas configuracoes. O Ollama realiza a inferencia; os comandos `/ruflo` usam o Ruflo. Os provedores ChatGPT, OpenAI API e Codex CLI continuam opcionais e estao sujeitos aos requisitos e limites proprios.

## Local data

Use **Help > Open Data Folder** para localizar os dados. O JEW preserva os nomes legados de pasta do Clew para nao quebrar perfis existentes. Localizacoes usuais:

| System | Application data |
| --- | --- |
| Windows | `%APPDATA%\clew\data` |
| macOS | `~/Library/Application Support/clew/data` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/clew/data` |

`knowledge_graph.sqlite3` stores the workspace, snapshots, chats and quizzes.
`chatgpt-registration.json` so e utilizado quando o provedor ChatGPT esta configurado. Os tokens ChatGPT opcionais sao armazenados no cofre do sistema (Keychain, Windows Credential Locker ou Secret Service). Chaves opcionais da API possuem tratamento de credenciais separado. O perfil de smoke test e isolado dos dados de uso cotidiano.

O app instalado mantem dados independentes do checkout em `backend/data`. Transporte grafos por exportacao/importacao e faca backup de toda a pasta de dados com o aplicativo fechado. Desconectar a conta ChatGPT nao remove os grafos. A instalacao nao inclui pesos de modelos Ollama nem o Ruflo.

Use **Help → Open Logs** for startup diagnostics. Logs must not contain OAuth codes, tokens, or the private launch session. Report errors with your platform, Clew version, and redacted relevant log entries.

The launcher sets `KG_DEBUG_LOG_DIR` to the writable `backend` directory inside
Electron's log folder. It never writes diagnostics into the application bundle.

**Help > Check for Updates** depende da configuracao de um repositorio de releases do JEW. Sem essa configuracao, a verificacao pode estar indisponivel. Nao interprete releases do Clew como atualizacoes do JEW. Atualizacoes do JEW permanecem manuais; nao existe promessa de download ou instalacao automatica. O macOS precisaria de assinatura apropriada para seu atualizador nativo.

## Development

For browser development on macOS/Linux, use `./scripts/dev.sh`. For Electron development, first set up `.venv`, install the backend and frontend, then run `npm ci && npm run dev`.

Use Node 22.22.2 or newer. CI packaging uses Python 3.12.

Native Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -e backend -r desktop/requirements.txt
npm ci
npm --prefix frontend ci
npm run dev
```

Native macOS/Linux:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -e backend -r desktop/requirements.txt
npm ci
npm --prefix frontend ci
npm run dev
```

## Build and verify

```bash
npm run package
npm run smoke:package
```

Build on the matching OS and architecture: PyInstaller embeds a native Python runtime. Cross-compiling only the Electron window does not produce a usable backend. Set `CLEW_PYTHON` when using an environment other than `.venv`.

macOS packaging requires cryptography with statically linked OpenSSL. Apple
Silicon wheels provide this; Intel builds may need compilation with Xcode tools,
Rust and `OPENSSL_STATIC=1`. The build rejects dynamic OpenSSL bindings before
freezing. Follow the [macOS source-build instructions](DESKTOP_RELEASE_VALIDATION.md#macos-cryptography).

O fluxo herdado de releases inclui Windows x64, macOS arm64/x64 e Linux x64/arm64, mas esta auditoria do JEW validou somente os testes e artefatos Windows citados no relatorio de 23/10/2026. Nao considere distribuicoes JEW para outras plataformas validadas sem um build e smoke test proprios.
Each job checks the native package, onboarding, stable storage, renderer isolation,
API boundary, export helper and shutdown. macOS signatures are verified. Linux
requires prepared native tools before packaging; see
[release validation](DESKTOP_RELEASE_VALIDATION.md). Tag builds prepare a draft
only after all jobs and artifact validation pass. The owner publishes it.
Assets include checksums, startup receipts and screenshots. Third-party Python,
JavaScript and native-library notices are bundled under `resources/LICENSES`;
Electron retains its own license files.

Um smoke test de instalador verifica o aplicativo empacotado, mas nao substitui um teste real da inferencia Ollama. A miniaula local com `qwen3.5:4b` foi executada em 23/10/2026. Na geracao real de quiz com seis questoes foi observado um indice de resposta incorreto (x/9 = 2/3, correto x = 6, indice marcado para 4). O validador numerico identifica esse caso, mas a qualidade matematica e conceitual de todo quiz ainda precisa ser auditada, e a validacao ponta a ponta de um quiz real aceito pela API continua pendente. Testes de autenticacao utilizam um peer isolado e nao comprovam consentimento, elegibilidade ou disponibilidade de planos ChatGPT em producao.
