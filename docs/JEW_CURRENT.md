# Jew 1.0.0 - guia atual de instalação, arquitetura e funções

**Atualizado em 24/10/2026.** Jew é um workspace local de aprendizagem estruturada em grafos. É uma adaptação do Clew, com código, dados e recursos legados preservados para compatibilidade. Os documentos de autenticação obrigatória Clew estão marcados como históricos. **Jew 1.0.0** é o identificador técnico atual; **JEW ULTIMATE 2.0** é a missão de evolução, ainda sem release validado.

## Histórico persistente de relatórios pedagógicos — implementado no código-fonte

- Cada quiz **enviado e corrigido** produz um `QuizReportRecord` versionado (`format_version=1`) com tentativa, relatório e análises por questão. O backend grava o registro na tabela SQLite `quiz_pedagogical_reports`, com chave primária `attempt_id` e índice por grafo, tópico e data. Registros anteriores à introdução desse recurso não são retroativamente convertidos em relatórios.
- `record_quiz_attempt()` grava o relatório, o novo snapshot e o consumo da sessão/rascunho em **uma transação**. Se a gravação falhar, a tentativa e o consumo da sessão também são revertidos. O relatório é evidência de avaliação e não reabre nem altera o estado acadêmico sozinho.
- `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports?limit=20&offset=0` lista tentativas em ordem de data e ID; `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}` recupera o relatório original. Paginação inválida retorna 422; grafo/tópico/tentativa ausente retorna 404; formato histórico incompatível retorna 409; conteúdo corrompido retorna 500 sem incluir o payload na resposta.
- Rollback de snapshot **mantém** os relatórios como trilha de auditoria. O campo `in_current_graph` distingue tentativas removidas do estado atual pela restauração; elas não voltam a valer automaticamente como progresso. Exclusão definitiva do grafo remove seus relatórios. A ordem acadêmica das tentativas presentes no grafo continua sendo a ordem persistida no array, independente da ordenação cronológica da listagem.
- No frontend, o popover do tópico oferece **Ver relatórios anteriores**. `StudyReportHistory` permite paginação, detalhes, retorno à lista, tratamento de vazio/erro/retry, cancelamento de requisições obsoletas e fechamento acessível. A seleção de outro grafo ou tópico encerra a consulta anterior, sem interferir diretamente no quiz ativo.
- Os diagnósticos continuam limitados à evidência disponível: `error_category="undetermined"` e `diagnosis_confidence="insufficient"` quando a causa não pode ser inferida. As análises de questões e os gabaritos ainda requerem julgamento pedagógico, e a interface diferencia gabaritos não verificados.

**Exportação PDF de relatório pedagógico: implementada no código-fonte.** Após enviar o quiz, abra **Ver relatórios anteriores**, selecione uma tentativa e use **Baixar relatório em PDF**. O endpoint `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}/pdf` exporta o registro persistido, inclusive quando a tentativa foi retirada do grafo atual por rollback. O arquivo A4 tem texto selecionável, páginas numeradas, cabeçalho, resultados por questão, observações e plano de recuperação, além da marca d'água obrigatória **DAniel Schirmer Project JEW** em cada página. O download usa a sessão privada do desktop quando configurada, sem exigir login ChatGPT para estudar dados locais. Há limites de tamanho e mensagens de falha genéricas para evitar exposição de conteúdo interno.

**Limites atuais do PDF:** apenas o relatório de quiz submetido é exportável. Ainda faltam PDFs de aulas, resumos, plano de estudo, roadmap e variantes de quiz; composição de desenhos/rascunhos; renderização matemática especializada para LaTeX; e validação visual e operacional em aplicativo distribuído e leitores externos. O script de build passou a incluir os recursos do ReportLab, mas **a inclusão no executável e o funcionamento no instalador ainda precisam de teste com nova compilação**. A exportação JSON/Obsidian permanece disponível. A matriz de escopo e testes está em [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Estado auditado da evolução acadêmica (24/10/2026)

- O endpoint `GET /api/v1/graphs/{graph_id}/learning-plan` oferece orientação determinística com evidências, regras, pré-requisitos e revisão espaçada heurística; a interface `LearningGuidance` apresenta essas decisões. Não existe demonstração empírica de melhoria de aprendizagem.
- O histórico acadêmico usa a **ordem de inserção no array persistido** para definir o evento mais recente. Quiz, conclusão manual, certificação, API, frontend, contexto do agente e importação/exportação respeitam essa sequência; `created_at` é usado para cálculos de intervalo de revisão, não para reordenar eventos. Registros legados podem ter timestamps empatados ou incoerentes.
- Submissão de quiz consome sua sessão dentro da mesma transação SQLite que insere o snapshot. A conclusão manual também invalida sessões antigas na transação do novo snapshot. Uma regressão com dois repositórios/conexões concorrendo pela mesma sessão exige um único vencedor, uma tentativa e um snapshot adicional.
- Na importação de grafos, IDs duplicados, referências inexistentes, ciclos de pré-requisitos e tentativas de quiz associadas a tópicos ausentes são rejeitados antes de criar snapshots. Também são rejeitados pacotes com `kind` diferente de `mapmind_graph_export`, versão diferente de `1` e históricos de quiz com IDs vazios ou duplicados. Um pacote legado com histórico de quiz inválido ainda pode ser importado com `include_progress=False`, descartando o histórico de progresso; formato/versão incompatível e ciclos no grafo continuam proibidos.
- **Validação executada em 24/10/2026:** backend `250/250` testes, incluindo retorno HTTP 400 para importação cíclica e para formatos/históricos inválidos; frontend `146/146` testes, TypeScript aprovado e build Vite aprovado; Electron `22/22` testes. O chunk `Graph3DCanvas` produzido pelo build tem aproximadamente `594,12 kB` e aciona aviso de tamanho, sem falha de build. As verificações do frontend e desktop antecedem as correções de importação, restritas ao backend.
- Esses testes confirmam comportamentos implementados no ambiente de desenvolvimento. Não constituem prova de segurança total, de corretude matemática fora do escopo declarado, de aprendizagem superior ou de funcionamento de um instalador gerado com este código.

### Atualização de evidências — estabilização do PDF (24/10/2026)

Após a etapa de 250/146 testes documentada acima, o checkpoint de estabilização registrou **275 testes backend aprovados**, **172 testes frontend em 30 arquivos**, **22 testes Electron**, TypeScript aprovado e build Vite aprovado, com o aviso não bloqueante do chunk `Graph3DCanvas` de aproximadamente **594,12 kB**. Esses resultados amplos foram recuperados do checkpoint anterior e não foram reexecutados nesta revisão documental; as contagens anteriores são mantidas como histórico.

Nesta continuação, `backend/tests/test_quiz_report_pdf.py` foi executado novamente: **11/11 testes aprovados**. A bateria abrange controle de acesso, integridade, rollback, paginação, Unicode básico, fontes e tratamento de falhas. O gerador usa `KeepTogether` para preservar análises curtas de questões na mesma página, com fallback para a fonte `Vera.ttf` distribuída com ReportLab quando fontes de sistema não estão disponíveis. Esse fallback não cobre universalmente notação matemática avançada.

A inspeção visual do PDF sintético `JEW_exemplo_relatorio_pedagogico.pdf` cobriu **seis páginas A4**, com marca d'água **DAniel Schirmer Project JEW** confirmada em todas por extração de texto. As prévias não exibiram cortes ou sobreposições evidentes; algumas páginas deixam espaço em branco para manter cada análise curta agrupada. A revisão visual e os testes são evidências distintas. **Ainda não foram validados** leitores PDF externos nem novo instalador/desktop empacotado contendo essa implementação.

Consulte [o plano incremental](IMPLEMENTATION_PLAN.md), [o protocolo de pesquisa não executado](competition/RESEARCH_PROTOCOL.md) e [o roteiro da banca](competition/DEMO_12_MINUTES.md).

## Instalação local no Windows

1. Instale a distribuição **Jew** validada para Windows x64. Preserve o perfil antigo e faça backup do SQLite antes da atualização. Não remova diretórios Clew.
2. Instale [Ollama](https://ollama.com/download/windows). No CMD: `ollama pull qwen3.5:4b`; confira com `ollama list`.
3. Se quiser comandos Ruflo/MCP, instale `npm install -g ruflo@3.59.17`; confira com `ruflo --version`.
4. O JEW inicia `ollama serve` automaticamente sob demanda quando a CLI está disponível e não há servidor local ativo. Após cada geração, solicita a descarga do modelo com `keep_alive: 0` e encerra o processo do servidor se foi iniciado pelo próprio JEW. Se você já executa o Ollama fora do JEW (aplicativo, serviço ou terminal), ele permanece sob seu controle; o JEW descarrega o modelo utilizado, mas não encerra esse servidor externo. Para conferir a disponibilidade manualmente: `curl.exe http://127.0.0.1:11434/api/tags`.
5. Abra Jew, acesse **Settings > Model provider**, selecione **Ruflo + Ollama** ou **Ollama**, clique **Refresh models** e escolha o modelo instalado.
6. Crie ou selecione um grafo, abra um tópico, gere uma aula e inicie um quiz. Os pré-requisitos do tópico precisam estar fechados para o quiz de conclusão.

O modelo local não consome créditos comerciais de geração da OpenAI, não depende de login ChatGPT nem de assinatura. Não há quota comercial de chamadas para a inferência local, mas uso continuado depende de RAM, CPU, armazenamento, energia e disponibilidade do serviço. Conteúdo da IA, especialmente operações matemáticas, requer revisão.

## Provedores

| Nome na interface | Identificador | Requisitos e operação |
| --- | --- | --- |
| Ruflo + Ollama | `ruflo_native` | Modelo Ollama local para aula, chat e quiz; comandos e MCP Ruflo opcionais. |
| Ollama | `ollama` | Inferência direta local; modelo instalado e serviço ativo. |
| ChatGPT via Codex | `codex_cli` | Instalação da CLI oficial, `codex login` e plano elegível; os limites do serviço permanecem. |
| OpenAI API | `openai_api` | Chave de API e possibilidade de cobrança por uso. |
| ChatGPT direto | `chatgpt` | Autenticação e uso de plano elegível; limites e falhas específicos desse provedor. |

O Ruflo é uma camada de ferramentas/orquestração, não executa sozinho um modelo de linguagem. Falhas de Ollama devem aparecer explicitamente e não autorizar migração automática para APIs pagas. O provedor pode ser trocado sem apagar dados de estudo.

## Recursos da aplicação

O Jew gerencia múltiplos grafos de estudo com tópicos, níveis, estados, dependências de pré-requisito e zonas. Permite criar, renomear e excluir grafos; aplicar propostas de alterações após revisão; organizar nós e posições; alternar visualizações 2D/3D; e acompanhar o fechamento e revisão de tópicos. Conta com painel de avaliação, recursos web por tópico, anotações/artefatos e importação/exportação de grafos e materiais de Obsidian.

O assistente mantém chats por grafo, sessões, histórico de mensagens e interações com ferramentas. Pode ler o contexto do grafo, apresentar questões e propor expansão/ingestão. Propostas são validadas e só passam a modificar grafos quando aplicadas. O histórico persistido permite reconexão e os snapshots permitem recuperação de estados.

**Aulas:** endpoint `POST /api/v1/graphs/{graph_id}/topics/{topic_id}/lessons/generate`; modelo selecionável, estrutura validada, repetição de respostas inválidas e artefato de aula persistido/versionado por tópico. Exibição Markdown/KaTeX no frontend e histórico de versões.

**Quizzes:** o fechamento solicita de 6 a 12 questões com quatro opções. O backend valida a estrutura, guarda o gabarito fora da resposta pública, calcula nota, aplica limiar e bloqueio de pré-requisitos, grava tentativa e atualiza progresso. Ações manuais de **Finish** registram `source=manual`; aprovação em prova registra `source=quiz`. O valor de nota fictício nos registros manuais não deve ser confundido com resultado de avaliação formal; o frontend distingue a origem.

**Verificação aritmética no código-fonte (24/10/2026):** a nova camada determinística rejeita erros de gabarito demonstráveis em operações aritméticas, frações, porcentagens e equações lineares simples, bem como alternativas numéricas equivalentes. A checagem atua antes da gravação e da correção, inclusive sobre sessões legadas. Cada questão pode estar marcada como `verified` ou `unverified`; a interface avisa quando a verificação automática é insuficiente. Esse estado **não comprova exatidão universal**, e outras áreas e notações matemáticas continuam exigindo revisão. O instalador 1.0.0 construído em 23/10/2026 **não contém necessariamente essas alterações recentes**. Veja [plano e política da verificação](IMPLEMENTATION_PLAN.md).

## Arquitetura e integridade

| Camada | Responsabilidades | Diretório |
| --- | --- | --- |
| React/TypeScript | UI, canvas 2D/3D, conversas, quiz, aulas, configurações | `frontend/src/` |
| Electron | Aplicativo Windows, processo backend, protocolo local, IPC, perfil e empacotamento | `desktop/` |
| FastAPI | Rotas REST, validação, fluxos de estudo e chat | `backend/app/api/` |
| Agent runtime | Seleção dos provedores, clientes Ollama/ChatGPT/Codex/API, ferramentas, eventos | `backend/app/agent/` |
| Serviços acadêmicos | Regras de quiz, avaliação, propostas, persistência | `backend/app/services/` |
| SQLite | Grafos, snapshots, aulas, quizzes, progresso e mensagens | perfil do usuário |
| MCP local | Leitura estruturada de grafos/tópicos/contexto | `backend/app/mcp_server/` |

As alterações estruturais usam validação de grafo/revisão e snapshots. A persistência usa transações SQLite; sessões de quiz são consumidas no envio e uma tentativa não deve ser duplicada. O desktop usa loopback e sessão privada, verificação de origem/CSP, renderer isolado, IPC restrito, sanitização de URLs/caminhos e logs com remoção de segredos. Esses controles são evidências de implementação e testes, não substituem auditoria externa de segurança ou prova formal de ausência de races.

## Desenvolvimento, testes e distribuição

É necessário Node.js 22.22.2+ e Python suportado pelo backend (recomenda-se Python 3.12 no empacotamento Windows). Na raiz do repositório:

```powershell
npm ci
npm ci --prefix frontend
py -3.12 -m venv .venv-official
.\.venv-official\Scripts\python.exe -m pip install -e .\backend
.\.venv-official\Scripts\python.exe -m pip install -r .\desktop\requirements.txt
$env:CLEW_PYTHON = (Resolve-Path .\.venv-official\Scripts\python.exe).Path
npm run dev
```

Para validar:

```powershell
.\.venv-official\Scripts\python.exe -m pip install -e '.\backend[test]'
$env:PYTHONPATH = 'backend'
.\.venv-official\Scripts\python.exe -m unittest discover -s backend/tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm run test:desktop
npm run check:version
npm run package
npm run smoke:package
```

O instalador é gerado em `desktop/artifacts`. O smoke utiliza perfil temporário isolado e verifica inicialização, API/sessão e dados entre reinicializações. A instalação para uso comum já inclui o backend empacotado; não é necessário instalar Python para usar o executável.

## Garantias e limitações

**Validação Windows em 23/10/2026:** 199 testes backend, 136 testes frontend e 22 testes Electron passaram; o instalador `Jew-1.0.0-win-x64.exe` concluiu build e smoke em perfil isolado, incluindo persistência entre reinícios, proteção de sessão e parada do backend. O SHA-256 do pacote é `DFB3DAF4391D41912AEAC3085E5C179CE1E249ADB69FC6921BD87FFB34C84F53` (141.218.684 bytes). A verificação Authenticode identificou o instalador como **NotSigned**; o arquivo legado `desktop/artifacts/latest.yml` ainda aponta para Clew, e atualização automática JEW não foi validada. Essas limitações devem ser resolvidas antes de uma distribuição pública assinada.

Dados de usuário permanecem locais, mas instalação, desinstalação, importação, rollback e migração precisam de backup antes de operações com potencial de perda. Não faça reset destrutivo em perfis. A inferência local depende do modelo baixado. Um quiz tecnicamente válido pode conter erro factual/matemático. Quizzes com respostas previamente conhecidas validam fluxo de correção e persistência, não provam que todo gabarito gerado seja correto. Desempenho em modelos locais varia de acordo com hardware.

Para histórico de decisões originais, consulte as [ADRs](adr/README.md). Para detalhes de empacotamento e perfil, consulte [Desktop](DESKTOP.md).
