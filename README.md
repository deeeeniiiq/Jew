# Jew 1.0.0

Guia consolidado da arquitetura e uso atual: [Jew 1.0.0 - guia completo](docs/JEW_CURRENT.md). Alguns documentos herdados do Clew foram preservados como histórico e estão identificados como tal.

**Workspace local de estudos com grafos e assistente de IA opcional.**

Jew transforma objetivos e notas em mapas de assuntos com dependências, progresso, quizzes e conversas. As propostas de IA passam por revisão antes de alterar grafos; snapshots permitem recuperar estados anteriores.

Este projeto é uma adaptação do [Clew original](https://github.com/miuuyy/Clew), de Aleksandr Vechenkov, sob a licença MIT ([LICENSE](LICENSE)). A documentação e os downloads do Clew original não representam uma distribuição Jew.

## Ruflo + Ollama: aulas e quizzes sem créditos

**Ruflo + Ollama é o modo padrão de novas instalações do Jew.** Os comandos do Ruflo usam ferramentas MCP, memória local e metadados de swarms; aulas, explicações e quizzes gerados por IA usam um modelo instalado no Ollama. Esse fluxo não precisa de assinatura ChatGPT, autenticação GPT/Codex, chave OpenAI ou créditos comerciais. Os dados do workspace continuam locais.

**Limitação técnica:** Ruflo é um orquestrador e um conjunto de ferramentas; sozinho não gera texto. Para aulas e quizzes, o Jew usa o Ollama local. Se ele estiver desligado ou não houver modelo instalado, a interface informa a indisponibilidade e os comandos `/ruflo` e `/help` continuam funcionando. Não há fallback automático para APIs pagas. O uso local não tem cotas de tokens de provedores comerciais, mas depende de RAM, CPU, energia e do modelo instalado.

No Windows, instale [Ollama](https://ollama.com/download/windows) e, no CMD, execute:

```bat
ollama pull qwen3.5:4b
ollama list
```

Mantenha o Ollama aberto. No Jew, acesse **Settings → Model provider → Ruflo + Ollama**, atualize os modelos locais e escolha **qwen3.5:4b** (ou outro modelo instalado e compatível). O modelo `qwen3.5:4b` foi usado em testes reais de explicações e geração de questões em 23/10/2026. A explicação em português foi produzida; uma geração de quiz apresentou um gabarito matematicamente inconsistente e foi identificada pelo validador. Portanto, a qualidade pedagógica das avaliações geradas por modelos locais ainda requer revisão, e quizzes podem ser rejeitados após novas tentativas. Para um Ryzen 5 5600G com 16 GB de RAM, o modelo de 4 bilhões de parâmetros é uma opção inicial, mas respostas na CPU podem levar vários minutos. Uma instalação nova não inclui o Ollama nem os pesos do modelo.

No Windows, instale [Node.js](https://nodejs.org/) compatível com o projeto e depois execute no CMD:

```bat
npm install -g ruflo@3.59.17
ruflo --version
```

Abra as configurações do Ruflo no Jew, clique **Check connection** e verifique **Ruflo MCP connected**. Se o comando global não estiver disponível, o adaptador tenta uma versão já presente no cache `npx`, sem fazer download automático. Em uma instalação limpa, o Node.js e o Ruflo precisam ser instalados separadamente; o instalador Jew não os inclui. A versão 3.59.17 é a que foi validada no Windows.

O chat no modo nativo aceita estes comandos explícitos:

```text
/help
/ruflo status
/ruflo agents
/ruflo swarm status
/ruflo swarm init mesh
/ruflo memory store estudo "Matemática: revisar integrais"
/ruflo memory search "Matemática: revisar integrais"
```

As notas da memória Ruflo ficam em um banco isolado do banco principal do Jew, no namespace `jew`. Pesquise pelo **conteúdo** das notas para melhores resultados: a pesquisa é semântica e usa limiar de similaridade. O Ruflo não altera os grafos automaticamente. Inicializar um swarm cria metadados de orquestração; não inicia inferência por IA. Se o Ruflo não estiver instalado ou estiver indisponível, o Jew continua abrindo o workspace e exibe o erro de conexão.

## Provedores opcionais de IA

É possível **abrir o workspace sem login ChatGPT e sem assinatura Plus/Pro**. Em **Settings → Model provider**, escolha:

| Provedor | Requisito | Cobrança |
| --- | --- | --- |
| **Ruflo + Ollama (padrão)** | Ollama + modelo local; Node.js/Ruflo para comandos MCP | Aulas, quizzes, memória e ferramentas locais, sem créditos comerciais |
| **Ollama** | Ollama local com modelo compatível com chamadas de ferramentas | Processamento local, sem assinatura ChatGPT |
| **ChatGPT via Codex CLI** | Codex CLI oficial instalado e autenticado com `codex login` | Sem chave ou créditos da OpenAI API; sujeito à elegibilidade e aos limites do ChatGPT/Codex |
| **OpenAI API** | Chave de API válida, verificada em Settings | Cobrança da API independente do ChatGPT |
| **ChatGPT** | Login OAuth, conta elegível e autorização de compartilhamento de plano | Conforme o plano e os limites aplicáveis |

Os provedores comerciais são opcionais e exigem seleção explícita; podem ter custos ou limites próprios. Contas ChatGPT gratuitas podem não ser elegíveis para compartilhar o plano via OAuth. O aplicativo não contorna as regras de autorização da plataforma.

Para usar Ollama, instale e inicie o serviço local (padrão: `http://127.0.0.1:11434`), baixe um modelo com suporte a ferramentas usando `ollama pull <modelo>`, selecione **Ollama** nas configurações, salve e atualize a lista de modelos.

Para OpenAI API, selecione **OpenAI API**, preencha sua chave e clique **Verify & save**. A chave é validada antes de substituir a anterior e fica criptografada com DPAPI no Windows. Também há suporte à variável de ambiente `OPENAI_API_KEY`. API e assinatura ChatGPT são serviços distintos.

Para ChatGPT, selecione **ChatGPT** e **Continue with ChatGPT**. O navegador retorna à rota local `/auth/callback`; o backend precisa estar em execução. Erros de elegibilidade do ChatGPT não impedem usar os outros provedores.

Para usar o **Codex CLI como intermediário**, instale a CLI oficial com `npm install -g @openai/codex` e execute `codex login` no CMD. Escolha **Sign in with ChatGPT** (sem chave de API), confira com `codex login status`, abra **Settings → Model provider → ChatGPT via Codex**, salve e clique **Refresh models**. Escolha **Automatic**; modelos específicos do ChatGPT Web, inclusive identificadores `chatgpt-web/*`, podem não estar disponíveis na CLI. Esta integração não garante acesso a GPT-6 Sol Web ou uso ilimitado de modelos pagos. Nenhum fallback para cobrança da OpenAI API é utilizado neste provedor.

## Exportar relatório pedagógico em PDF

A exportação disponível atualmente abrange **relatórios de quizzes já enviados e corrigidos**. Para baixar um relatório no Jew:

1. Responda e **envie** um quiz para registrar a tentativa.
2. Abra o **tópico** correspondente no grafo.
3. Selecione **Ver relatórios anteriores** no menu do tópico.
4. Escolha a **tentativa** desejada, inclusive uma tentativa histórica anterior a um rollback.
5. Clique em **Baixar relatório em PDF** para salvar o arquivo.

O PDF A4 inclui informações da tentativa, resultados, análise das questões, orientações para revisão e a marca d'água **DAniel Schirmer Project JEW** em todas as páginas. A paginação procura manter cada análise curta inteira, e o texto é selecionável. Só é possível exportar tentativas com relatório persistido; quizzes em andamento e registros antigos sem relatório não oferecem esta exportação.

**Limitações atuais:** não há exportação PDF de aulas, resumos, planos, roadmap ou versões em branco/respondidas/corrigidas de quizzes; desenhos não são compostos no documento; fórmulas LaTeX avançadas e todos os caracteres matemáticos ainda não são suportados. A geração foi testada no código-fonte e as seis páginas de um exemplo sintético foram inspecionadas, mas a funcionalidade **não foi validada em um novo instalador Electron nem em leitores PDF externos**. Veja [detalhes e evidências](docs/IMPLEMENTATION_PLAN.md) e [estado atual](docs/JEW_CURRENT.md).

## Compilar no Windows x64

Requer Node.js 22.22.2+, Python compatível com `backend/pyproject.toml` (recomendado 3.12 para build Windows), ferramentas do Electron Builder e as dependências de backend/desktop. Veja também [Desktop development](docs/DESKTOP.md).

No PowerShell, na raiz do repositório:

```powershell
npm ci
npm ci --prefix frontend
py -3.12 -m venv .venv-official
.\.venv-official\Scripts\python.exe -m pip install -e .\backend
.\.venv-official\Scripts\python.exe -m pip install -r .\desktop\requirements.txt

$env:CLEW_PYTHON = (Resolve-Path .\.venv-official\Scripts\python.exe).Path
npm run check:version
npm run build
npm run package
npm run smoke:package
```

Os resultados ficam em `desktop/artifacts`. O smoke utiliza um perfil isolado. Para desenvolvimento, execute `npm run dev` depois de instalar as dependências.

## Dados e compatibilidade

Faça backup antes de instalar. O perfil histórico de Windows pode estar em `%APPDATA%\clew`, com SQLite em `data\knowledge_graph.sqlite3`. Jew reaproveita esse perfil quando detecta o banco anterior. **Não exclua nem migre manualmente os dados Clew durante a atualização.**

Alguns identificadores internos, como `clew://app`, `X-Clew-Session` e nomes de executáveis auxiliares, permanecem para compatibilidade com instalações antigas. Nome comercial e interface são Jew. Grafos, snapshots, conversas, progresso e exportações continuam locais. Sair da conta ChatGPT não apaga o workspace; a API do desktop preserva a autenticação local de sessão.

O perfil GitHub pode ser indicado em `VITE_JEW_GITHUB_URL` antes do build. O link Twitter/X fica em branco. As atualizações Jew exigem configurar um repositório próprio de releases; o projeto não apresenta os releases Clew como se fossem Jew.

## Testes

```powershell
.\.venv-official\Scripts\python.exe -m pip install -e '.\backend[test]'
$env:CLEW_PYTHON = (Resolve-Path .\.venv-official\Scripts\python.exe).Path
$env:PYTHONPATH = 'backend'
.\.venv-official\Scripts\python.exe -m unittest discover -s backend/tests -q
npm run test:desktop
npm run typecheck --prefix frontend
npm run test --prefix frontend
npm run check:version
```

Arquitetura: `desktop/` (Electron e empacotamento), `frontend/` (interface), `backend/app/` (agentes, API, persistência), `contracts/` (contratos) e `docs/` (documentação). Licença e atribuição original preservadas.
