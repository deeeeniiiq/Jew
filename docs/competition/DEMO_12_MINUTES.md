# JEW ULTIMATE — demonstração acadêmica de 12 minutos

**Situação em 24/10/2026:** roteiro de apresentação, não registro de uma apresentação realizada. Use a versão do código-fonte validada no dia da banca. O instalador Jew 1.0.0 histórico pode não incluir as melhorias recentes.

**Evidência de engenharia disponível em 24/10/2026:** `244` testes de backend, `146` de frontend e `22` de Electron passaram; TypeScript e build Vite passaram. Para explicar concorrência, demonstre em terminal, usando o **banco temporário criado pelo teste**, `test_simultaneous_submissions_of_same_session_have_single_winner` em `backend/tests/test_repository_concurrency.py`: dois envios simultâneos da mesma sessão resultam em um só registro de quiz. Essa demonstração não deve ser feita no banco de um estudante. O build informa aviso não impeditivo para o bundle 3D de aproximadamente `594,12 kB`.

## Preparação e segurança dos dados

1. Em uma cópia de demonstração ou perfil temporário, abra o JEW com o backend local. Faça backup antes de usar qualquer perfil preexistente. Não altere bancos reais para a banca.
2. Garanta acesso ao grafo **Mathematics demo**, definido em `backend/app/services/bootstrap.py` como *seed* sintético, com nove tópicos e relações `requires`, `supports` e `bridges`. A instalação de um perfil novo pode começar vazia: nesse caso, prepare um grafo próprio na UI ou use uma cópia de demonstração isolada.
3. Abra um tópico e confira a seção **Learning guidance**. O plano é calculado em `GET /api/v1/graphs/{graph_id}/learning-plan` a partir do estado persistido. O frontend descarta respostas de outro grafo ou versão.
4. Configure Ollama e um modelo já instalado, se a parte generativa estiver planejada. Teste previamente a geração de aula e quiz. Sem modelo disponível, use aulas/questões **previamente geradas e identificadas como tal** e siga com as demonstrações determinísticas.
5. Prepare backup visual ou captura de tela apenas como contingência. Identifique claramente qualquer captura estática. Nunca apresente uma captura como ação executada ao vivo.

## Sequência sugerida

| Tempo | Demonstração | Evidência observável |
| --- | --- | --- |
| 00:00–01:00 | Problema: estudar tópicos isolados não explica dependências de conhecimento. | Exemplo de pré-requisito de álgebra para funções. |
| 01:00–02:00 | Proposta: JEW integra grafo, material, avaliação e progresso local. | Interface desktop e navegação geral. |
| 02:00–03:15 | Navegar no grafo 2D/3D; diferenciar `requires`, `supports`, `bridges`. | Grafo e tópico selecionado. |
| 03:15–04:15 | Percurso: aritmética → álgebra → funções. | Dependências e bloqueios de conclusão. |
| 04:15–05:30 | Abrir ou gerar uma aula; mostrar conteúdo Markdown/KaTeX e versão. | Aula armazenada por tópico ou fallback identificado. |
| 05:30–07:00 | Iniciar quiz, responder, mostrar correção e regra de aprovação. | Correção no backend e persistência de tentativa. |
| 07:00–08:10 | Apresentar um exemplo matemático reconhecível incorreto, **somente em teste/ambiente isolado**. | Validador determinístico rejeita gabarito demonstravelmente errado. |
| 08:10–09:15 | Mostrar diferença entre conclusão manual e certificação por quiz. | `source=manual` versus `source=quiz` e `closure_awarded`. |
| 09:15–10:30 | Abrir **Learning guidance** e explicar recomendação e pré-requisitos. | Ação, evidências, regra, condição de saída e revisão sugerida. |
| 10:30–12:00 | Evidências de engenharia, limites e perguntas. | Testes executados, ausência de prova de eficácia, planos de validação. |

## Evidência sintética reproduzível

O script `docs/competition/generate_demo_fixture.py` usa o grafo demonstrativo do próprio projeto e **não acessa SQLite, IA ou perfis pessoais**. Produz `docs/competition/demo_fixture.synthetic.json` contendo grafo e plano derivados de três tentativas inventadas exclusivamente para teste, com data fixa de 24/10/2026. Na raiz do repositório, execute:

```powershell
$env:PYTHONPATH = 'backend'
.\.venv-official\Scripts\python.exe docs/competition/generate_demo_fixture.py --output docs/competition/demo_fixture.synthetic.json
```

Para esta versão do código e da fixture, o resultado esperado é: **9 tópicos, 2 concluídos, 1 certificado por quiz, 1 somente manual, 1 revisão vencida e 3 bloqueados**. Exemplos: `algebra-basics → practice`, `arithmetics → review`, `angles → verify`, `functions → unblock`. Os números servem para demonstrar **regras de software sobre dados simulados**; não são métricas educacionais de pessoas. O JSON é material de auditoria offline e não é carregado automaticamente na interface.

## Demonstração de um gabarito incorreto

O serviço matemático de escopo restrito analisa operações e formas reconhecidas. Para mostrar a proteção, use os testes automatizados de `backend/tests/test_mathematical_validation.py` e `backend/tests/test_quiz_service.py`, que exercitam casos rejeitados antes de gravar/atribuir nota. Não introduza questão errada em banco de estudante. Explique os estados `verified`, `rejected` e `unverified`: não reconhecer uma questão **não significa** que ela seja verdadeira ou falsa.

## Plano de contingência

- **Ollama lento ou indisponível:** demonstrar aula persistida previamente e a validação matemática determinística, deixando explícito que a geração não ocorreu ao vivo.
- **Problema com backend:** mostrar código, testes e fixture offline; registrar a falha. Não simular chamadas bem-sucedidas.
- **Grafo vazio:** utilizar perfil de demonstração separado preparado antes da banca. Não substituir silenciosamente dados pessoais pelo seed.
- **Sem acesso à internet:** usar operações locais. O modelo Ollama exige instalação prévia dos pesos, mas não depende de crédito de API para inferência local.

## Perguntas difíceis da banca

**Como sabem que o estudante aprendeu?** O sistema registra tentativas e estados; a regra heurística não prova aquisição de conhecimento. Uma avaliação controlada deve medir pré/pós-teste e retenção.

**A IA garante que a resposta está correta?** Não. O validador independente prova somente cálculos cobertos pela gramática implementada; itens não verificados permanecem explicitamente identificados.

**A recomendação é inteligência artificial?** É um motor determinístico e explicável, construído sobre o grafo e o histórico de avaliações. IA generativa é opcional para criação de conteúdo.

**Um ciclo no grafo permite certificação?** Não deve permitir. O serviço de quiz reavalia pré-requisitos transitivos e bloqueia ciclos e vínculos inválidos, inclusive se introduzidos após iniciar um quiz. Existem testes de regressão para esses casos.

**O que acontece sem assinatura ou créditos de API?** O modo Ollama executa geração local enquanto houver recursos computacionais e modelo instalado. Limites de hardware e confiabilidade do conteúdo continuam aplicáveis.

**O instalador está pronto para distribuição pública?** A versão histórica tem limitações documentadas, inclusive assinatura e confirmação de inclusão das mudanças recentes. Testes de código não equivalem a um novo instalador validado.

**Qual é a contribuição acadêmica?** A arquitetura conecta relações explícitas de pré-requisito, decisões pedagógicas auditáveis e validação matemática de escopo declarado. O impacto no aprendizado permanece hipótese a ser testada; consulte `RESEARCH_PROTOCOL.md`.
