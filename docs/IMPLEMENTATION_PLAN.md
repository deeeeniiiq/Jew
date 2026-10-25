# JEW Ultimate — implementação incremental e registro de riscos

Atualizado em 24/10/2026. Este registro distingue **evidência executada** de metas. A fonte primária é o código nesta árvore de trabalho; há alterações anteriores não commitadas que devem ser preservadas.

## Histórico durável de relatórios — implementação e contrato (24/10/2026)

O histórico de relatório pedagógico foi integrado aos fluxos atuais de quiz. O tipo `QuizReportRecord` em `backend/app/models/domain.py` fixa `format_version=1` e valida os vínculos entre IDs de tentativa, tópico, relatório, questões e análises. A tabela `quiz_pedagogical_reports` em `backend/app/services/repository_storage.py` usa `attempt_id TEXT PRIMARY KEY`, `graph_id`, `topic_id`, `created_at`, `format_version` e `payload_json`; há índice `idx_quiz_reports_graph_topic_date`. Sua criação é aditiva e preserva snapshots e sessões existentes.

Em `backend/app/services/repository.py`, a submissão da avaliação inicia `BEGIN IMMEDIATE`, consome exatamente uma sessão, elimina o rascunho, insere o snapshot e persiste o relatório na **mesma transação**. Falha em qualquer etapa reverte todas as mutações. A consulta usa `ORDER BY created_at DESC, attempt_id DESC`, com `limit` de 1 a 100 (`20` por padrão) e `offset >= 0`. A listagem valida o conteúdo de cada registro retornado, inclusive versão e metadados, antes de apresentá-lo. Uma restauração não exclui evidência histórica; `in_current_graph=false` sinaliza que aquela tentativa já não consta no grafo restaurado. Exclusão definitiva do grafo elimina os respectivos relatórios.

Contratos expostos em `backend/app/api/routes.py`:

| Endpoint | Resposta | Observação |
| --- | --- | --- |
| `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports` | `{items,total,limit,offset}` | Cada item traz ID, título, data, nota, número de questões e vínculo com o grafo atual. |
| `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}` | `QuizReportRecord` com `in_current_graph` | Retorna o relatório, a tentativa e as análises imutáveis da submissão. |
| `POST /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/submit` | Tentativa, revisão, relatório e workspace atualizado | Grava o registro histórico atomicamente. |

Erros explícitos: `404` para recursos inexistentes, `422` para parâmetros de paginação inválidos, `409` para versão incompatível e `500` para integridade comprometida. O corpo da resposta de integridade não divulga o JSON armazenado.

No React, o botão `Ver relatórios anteriores` do popover usa `WorkspaceApp` para abrir `StudyReportHistory`, isolado do estado da avaliação ativa. O componente valida resposta de listagem/detalhe, pagina em blocos de 10, cancela consultas obsoletas, mostra tentativas anteriores a rollback e permite retry. O `Modal` compartilhado fornece semântica de diálogo e tratamento de foco/teclado. Os estilos foram adicionados a `frontend/src/styles/components/study.css` e `popover.css`.

Cobertura específica: `backend/tests/test_quiz_report_history.py` (8 cenários incluindo persistência após reabertura, paginação, rollback, exclusão, atomicidade, formato e corrupção), `frontend/src/components/study/StudyReportHistory.test.tsx` e `frontend/src/WorkspaceApp.quiz.test.tsx` (navegação, falhas, cancelamento e convivência com quiz). Não há migração de relatórios antigos, contestação de correção implementada nem garantia automática de verdade das análises geradas. A evolução histórica só deve comparar tentativas quando a evidência permite.

## Exportação PDF — primeira modalidade implementada (24/10/2026)

O serviço `backend/app/services/pdf_export.py` usa ReportLab para criar **PDF A4 do relatório de uma tentativa já enviada e persistida** (`QuizReportRecord`). O endpoint `GET /api/v1/graphs/{graph_id}/topics/{topic_id}/quiz/reports/{attempt_id}/pdf` reutiliza a validação de escopo, versão e integridade da consulta individual e devolve um anexo `application/pdf`, com `Cache-Control: no-store` e `nosniff`. Tentativas anteriores a rollback são identificadas no próprio documento. A interface `StudyReportHistory` permite iniciar, cancelar e repetir o download, validando MIME, assinatura `%PDF-` e conteúdo não vazio. O endpoint exige `x-clew-session` quando um token de sessão desktop está configurado.

O PDF contém nota, metadados, análise por questão, respostas e gabaritos registrados, limites das evidências, recuperação e próximos passos. Utiliza fontes TrueType do sistema, com fallback para a `Vera.ttf` incluída no ReportLab, conteúdo textual escapado, limite de tamanho, texto selecionável, paginação, cabeçalho/rodapé e marca d'água **`DAniel Schirmer Project JEW`** em todas as páginas. O fallback aumenta a portabilidade, mas não garante cobertura de todos os símbolos matemáticos Unicode. O renderer captura erros de layout conhecidos e a rota devolve erro genérico ao cliente. Não há renderização especializada de LaTeX, verificação matemática adicional nem inclusão automática de desenhos no PDF.

O `desktop/scripts/build-backend.cjs` declara `--collect-all reportlab` para incluir módulos e recursos/fontes fornecidos pela biblioteca durante o congelamento PyInstaller; o uso das fontes e o funcionamento do PDF ainda exigem verificação no executável e nos sistemas de destino. **A configuração de empacotamento foi ajustada; ainda não foi construída nem inspecionada uma nova distribuição Electron com a exportação PDF.** O `reportlab>=4.4,<5.0` é dependência de produção em `backend/pyproject.toml`; o `pypdf>=6.0,<7.0` pertence somente a `[project.optional-dependencies].test`. A CI instala `backend[test]`.

Matriz objetiva contra as seções 8, 10 e 15 do Prompt Mestre:

| Requisito | Estado no código atual | Passo verificável |
| --- | --- | --- |
| PDF de relatório com dados da tentativa | **Implementado e testado** | Validar visualmente em leitores PDF externos e no desktop efetivamente empacotado. |
| PDF de aula, resumo, plano e roadmap | Pendente; dados/artefatos parciais disponíveis | Criar templates separados por tipo; validar seleção de versão e fonte dos dados. |
| Quiz limpo / com respostas / com correções | Pendente | Definir políticas para revelar gabarito **apenas após** submissão ou para exportação expressamente autorizada. |
| Desenhos/rascunhos na folha exportada | Pendente; strokes normalizados no caderno | Projetar coordenadas por questão/página; comparar sobreposição ao conteúdo renderizado e persistência. |
| Matemática, Unicode e texto selecionável | Unicode básico e texto selecionável **testados**; LaTeX avançado pendente | Exercitar fontes/glifos matemáticos adicionais e renderizador especializado para fórmulas. |
| Paginação, margens, privacidade e nomes seguros | Paginação longa, análises curtas agrupadas, texto escapado, falha segura e nome fixo **testados**; exemplo sintético inspecionado | Inspecionar casos extremos e leitores externos. |
| Marca d'água em todas as páginas | **Implementada, conferida por extração de texto nas seis páginas do exemplo e inspecionada visualmente** | Conferir contraste e posição em documentos reais e leitores externos. |

Testes direcionados em `backend/tests/test_quiz_report_pdf.py`: **11/11 aprovados**, reconfirmados em 24/10/2026, com tentativa real, rollback, escopo e erros de integridade, PDF extenso com Unicode, tamanho máximo, token privado ausente/incorreto/correto, falha segura do renderer e captura de `LayoutError`. Duas regressões adicionais verificam o fallback para `Vera.ttf` sem fontes do sistema e a não divisão de análises curtas entre páginas. Para preservar enunciado, respostas, explicação e orientação juntos, `pdf_export.py` aplica `KeepTogether(question_story)` a cada análise; análises maiores que uma página podem exigir divisão, e o agrupamento pode deixar espaço em branco ao fim de certas páginas. O frontend tem **10 testes específicos** para histórico e download, inclusive falhas, retry e cancelamento de downloads obsoletos. Testes em desenvolvimento não comprovam o comportamento do instalador distribuído.

Auditoria visual de 24/10/2026: o exemplo sintético `JEW_exemplo_relatorio_pedagogico.pdf` foi gerado com **seis páginas A4**, texto selecionável e marca d'água confirmada em todas as páginas por extração de texto. Foram examinadas prévias renderizadas das seis páginas; títulos, metadados, cabeçalhos, rodapés e análises curtas estavam legíveis, sem cortes ou sobreposições evidentes. Na quarta página, há espaço em branco associado ao agrupamento das análises. Essa inspeção visual complementa os testes automatizados, mas não valida conteúdo pedagógico real, leitores externos nem distribuição Electron empacotada.

Evidências adicionais registradas no checkpoint de estabilização de 24/10/2026: **275 testes backend**, **172 testes frontend em 30 arquivos**, TypeScript aprovado, build Vite aprovado (com aviso de chunk `Graph3DCanvas` de ~594,12 kB) e **22 testes Electron**. Esses totais pertencem à execução registrada anteriormente, sem reexecução dessas suítes nesta revisão documental; apenas os 11 testes específicos de PDF foram reexecutados aqui. Os resultados históricos inferiores descritos adiante permanecem como evidência de suas respectivas etapas.

Sequência restante: (1) validar esta modalidade no backend congelado, no aplicativo Electron empacotado e em leitores PDF externos; (2) exportar versões de aulas/planos e variantes de quizzes com segregação de gabaritos; (3) compor anotações e matemática avançada, com testes visuais e de privacidade; (4) verificar caminhos de salvamento e funcionamento por sistema operacional. Todas as demais capacidades PDF permanecem em planejamento até implementação e testes próprios.

## Continuação verificada — concorrência e consistência acadêmica

Em 24/10/2026 foi acrescentado `test_simultaneous_submissions_of_same_session_have_single_winner` a `backend/tests/test_repository_concurrency.py`. O teste coordena leituras na mesma revisão por duas instâncias independentes de `GraphRepository` sobre um SQLite temporário, tenta consumir a mesma sessão e exige: **uma submissão bem-sucedida, um `RepositoryConflictError`, uma tentativa registrada, um snapshot adicional, sessão consumida e ancestralidade linear dos snapshots**. A implementação de produção existente atendeu a esses critérios, sem alteração adicional na lógica de consumo.

A auditoria confirmou que `record_quiz_attempt()` usa `BEGIN IMMEDIATE`, `DELETE` com verificação de `rowcount` e inserção do snapshot na mesma transação. `mark_topic_finished()` invalida sessões de quiz dentro da transação de conclusão. `QuizService.build_closure_status()`, `AdaptiveLearningService`, `routes.py`, `agent/context.py` e `frontend/src/lib/graph.ts` usam a ordem gravada das tentativas. A importação/exportação com progresso mantém o array; a sem progresso remove tentativas e redefine estados. Timestamps históricos não definem precedência do evento acadêmico; o motor de revisão ainda os utiliza para programar revisões e, portanto, depende da qualidade desse campo temporal.

Nova regressão reproduziu dois erros antes da correção: pacotes de grafos com ciclos de pré-requisitos (inclusive autorreferências) e pacotes com tentativas de quiz apontando para tópicos ausentes eram aceitos pela importação. `GraphRepository.import_graph_package()` agora bloqueia ambos antes do snapshot. O importador usa o mesmo detector de ciclos que a aplicação de propostas e permite descartar apenas o histórico inconsistente com `include_progress=False`. Testes de falha e recuperação verificam que entradas inválidas não alteram o snapshot atual e que a importação sem progresso permanece disponível.

Regressões adicionais reproduziram a aceitação silenciosa de formatos/versões de pacote desconhecidos e IDs de tentativas de quiz duplicados ou vazios. A importação agora aceita apenas `kind=mapmind_graph_export` e `version=1`, valida IDs de tentativas quando o progresso é solicitado e devolve HTTP 400 para os novos erros na API. `include_progress=False` continua permitindo recuperar grafos estruturalmente válidos com histórico inconsistente, mas não ignora incompatibilidade de formato ou versão.

### Evidência atual de testes (24/10/2026)

| Verificação | Resultado desta continuação |
| --- | --- |
| Backend completo após as regressões de importação | **250 testes passaram** (28,095 s na última execução) |
| Frontend Vitest | **146 testes passaram** em 27 arquivos |
| TypeScript `tsc --noEmit` | **Aprovado** |
| Electron `npm run test:desktop` | **22 testes passaram** |
| Vite `npm --prefix frontend run build` | **Aprovado com aviso** de chunk 3D com ~594,12 kB |

**Pendências:** melhorias no carregamento do módulo 3D, cobertura global de internacionalização, teste de instalação/atualização Windows usando nova compilação, assinatura de release, benchmark de inferência Ollama em hardware-alvo e execução do protocolo de pesquisa com participantes. O instalador histórico Jew 1.0.0 não pode ser apresentado como incorporando essas mudanças. Nenhum efeito pedagógico de participantes foi medido.

Os **209 testes backend, 136 frontend e 22 Electron** citados na seção original de validação abaixo são resultados históricos da etapa de verificação matemática, preservados para rastreabilidade; as métricas atuais estão acima.

## Matriz de riscos e critérios

| Prioridade | Risco / impacto | Probabilidade / reprodução | Dependências e esforço | Critério verificável |
| --- | --- | --- | --- | --- |
| P0 | Gabarito numérico errado prejudicar nota e progressão | Alta em geração sem validação; exemplo `7 × 8 = 54` | Backend, baixo/médio | Questão com erro demonstrável rejeitada antes do SQLite e da correção |
| P0 | Sessão legada com gabarito inválido ser retomada | Possível; manipulação de sessão em teste | API e SQLite, baixo | API regenera sessão insegura; envio da antiga não grava tentativa |
| P0 | Alternativas matematicamente equivalentes e ambíguas | Reproduzível com `0,5` e `1/2` | Gramática numérica, médio | Detectar opções semanticamente equivalentes dentro da gramática |
| P1 | Conteúdo conceitual incorreto e matemática fora da gramática | Possível, difícil de provar automaticamente | Revisão de conteúdo, alto | Política explícita de não verificado; futura revisão especializada |
| P1 | IA local lenta, sem streaming/cancelamento apropriado | Depende de CPU/modelo | Ollama, testes em hardware real, alto | Benchmark repetível com percentis e cancelamento exercitado |
| P1 | Recomendações pedagógicas pouco justificáveis | Depende de histórico | Domínio, grafo, UI, alto | Recomendação determinística a partir de eventos persistidos |
| P1 | Concorrência/importação/perda de dados | Cenários complexos | SQLite, Electron, médio/alto | Testes de transação, backup, rollback e corrida em ambiente isolado |
| P2 | Sem estudo acadêmico ou demonstração reproduzível | Evidente pela ausência de estudo controlado | Protocolo, participantes e ética, alto | Instrumentos disponíveis; resultados apenas após coleta real |
| P2 | Distribuição sem assinatura e atualização JEW validada | Confirmado em relatório de 23/10 | Assinatura e release, médio | Instalador assinado e fluxo de atualização testado |

## Entregue nesta etapa: verificador aritmético limitado (P0)

- `backend/app/services/mathematical_validation.py` usa AST com nós permitidos, `Fraction`, teto de tamanho, complexidade, exponente e bits; não executa expressões fornecidas pela IA.
- Suporta enunciados padronizados em português/inglês de operações aritméticas, frações, porcentagem de quantidade, simplificação numérica e equações lineares de uma variável. Interpreta algumas notações básicas (`×`, `÷`, potências inteiras pequenas, vírgula decimal, `\\frac` numérico, delimitadores `\\(...)`).
- Compara resultado independente com a alternativa assinalada, detecta alternativas com mesmo valor, resultado ausente, divisão por zero, equação sem solução única e contradições matemáticas explícitas na explicação.
- `QuizService.start_session` executa a verificação antes de permitir a persistência. O Ollama pode pedir até três saídas e revalidá-las. Outros provedores passam pelo mesmo serviço de domínio.
- `QuizService.grade_session` revalida sessões existentes para impedir penalização em erros **comprovados**. O endpoint de início deixa de reutilizar sessões com contradições comprovadas, sem alterar históricos de tentativas.
- Metadados internos `verification_status` e `verification_version` permitem verificar a abrangência. Sessões históricas são lidas com estado `unverified`. A resposta pública só expõe o status, jamais o gabarito.
- Interface informa que itens fora da gramática ainda não foram automaticamente verificados.
- Revisão adversarial de 24/10/2026: corrigidos dois falsos positivos reproduzidos na leitura de explicações (`2x + 3 = 11` e `20% de 150 = 30`). O verificador agora ignora o fragmento escalar de uma equação simbólica e valida explicitamente o cálculo percentual, incluindo resultados incorretos. Testes de regressão foram adicionados.

### Validação executada em 24/10/2026

| Verificação | Resultado observado |
| --- | --- |
| Backend: `unittest discover -s backend/tests -q` | **209 testes passaram**, 28,897 s |
| Frontend: `vitest run --run` | **136 testes passaram**, 26 arquivos |
| TypeScript: `tsc --noEmit` | **Aprovado** (exit code 0) |
| Electron: `npm run test:desktop` | **22 testes passaram** |
| `git diff --check` | **Sem erros de whitespace**; avisos de futura conversão LF/CRLF |

Os testes do frontend foram executados antes da correção, restrita ao validador Python e seus testes. O backend completo foi reexecutado após a correção. Não foram executados novo build, smoke test de instalador, avaliação humana nem benchmark de inferência nesta etapa.

### Política de publicação

**Rejected:** bloqueado antes da persistência e do registro de notas, inclusive em sessões legadas.

**Verified:** exclusivamente quando expressão e todas as quatro alternativas são analisadas, existe uma única opção correspondente ao cálculo independente e a explicação não contém uma contradição reconhecida. Este selo vale apenas para o cálculo coberto, não para a qualidade pedagógica geral.

**Unverified:** conteúdo conceitual, texto ou notação matemática sem prova automática. Mantém a compatibilidade de avaliação existente, com identificação explícita na interface. **Ainda pode conter erros**; itens de alto impacto requerem revisão adicional. Uma futura política de bloqueio/revisão humana para avaliações de alta consequência deve ser definida antes de alegar confiabilidade universal.

### Limitações da implementação

- Não comprova respostas conceituais, enunciados de problemas em linguagem natural, equações quadráticas, logaritmos, unidades, domínio de funções, igualdade algébrica geral nem gráficos.
- Não usa SymPy; biblioteca ausente nos ambientes locais inspecionados. Gramática restrita evita carregar uma dependência pesada no empacotamento atual.
- Ausência de contradição detectável não equivale a prova de verdade; campos de explicação em linguagem natural podem conter erros não reconhecidos.
- Sessões antigas não são reescritas e notas históricas não são recalculadas.

## Próximas entregas verificáveis

1. Ampliar o corpus de referência independente para questões contextualizadas e provas de domínio, registrar falso positivo/negativo com métricas e tempo adicional da verificação.
2. Projeto de revisão semântica e pedagógica com confiança calibrada, citações verificáveis e feedback ao aluno; impedir avaliação injusta quando uma inconsistência for identificada.
3. Motor determinístico de domínio por tópico, revisão espaçada e recomendações explicáveis, com replay por histórico e UI 2D/3D.
4. Benchmark dos provedores locais, streaming, cancelamento e limites de tempo medidos em hardware real; evitar fallback comercial oculto.
5. Testes de segurança de importação, payloads malformados, concorrência, recuperação e proteção de dados; smoke isolado do desktop.
6. Cenário demonstrativo de Álgebra Fundamental e materiais de `docs/competition/`; protocolo de avaliação com participantes reais, sem métricas fabricadas.

## Comandos de validação

```powershell
$env:PYTHONPATH='backend;backend/tests'
.\.venv-official\Scripts\python.exe -m unittest discover -s backend/tests -q
npm --prefix frontend run typecheck
npm --prefix frontend run test -- --run
npm run test:desktop
```

Executar sempre em ambiente isolado. Não usar `git reset --hard`, `git clean` ou excluir dados pessoais. Preservar o instalador histórico 1.0.0, sem afirmar que incorpora estas alterações de fonte.
