# Protocolo proposto — avaliação educacional do JEW

**Estado:** protocolo de estudo ainda não executado. Não há participantes, coleta, resultados empíricos ou demonstração de superioridade registrados por este documento.

## Questão e hipóteses

Questão: em uma sequência de **Álgebra Fundamental**, o uso do JEW com grafo de pré-requisitos e orientação explicável melhora desempenho, retenção e entendimento do próprio progresso, em comparação com um percurso equivalente sem essas funcionalidades?

Hipótese primária prospectiva: diferença no desempenho de pós-teste de álgebra, ajustado pelo pré-teste. Hipóteses secundárias: retenção tardia, tempo de estudo, conclusão e usabilidade. O desenho deve ser registrado antes da coleta; os indicadores secundários não substituem o desfecho primário.

## Desenho proposto

- Dois grupos com alocação aleatória, quando institucionalmente viável: JEW e ferramenta/processo de referência com conteúdo, tempo e apoio comparáveis.
- Conteúdos e itens de avaliação construídos e revisados previamente por docentes independentes. Os testes de resultado não devem reutilizar questões exibidas em quizzes de treinamento.
- Pré-teste, período definido de intervenção, pós-teste e medida de retenção em intervalo pré-especificado (por exemplo, quatro semanas).
- Registrar experiência prévia, acesso a hardware e eventuais diferenças de conectividade/modelo; minimizar diferenças de contato docente entre grupos.
- Definir critérios de inclusão, exclusão, desistência e dados ausentes antes da coleta; estimar tamanho amostral via análise de poder com tamanho de efeito justificável, sem escolher amostra após olhar os resultados.
- Consentimento informado, minimização e anonimização de dados, plano de retenção e revisão ética institucional quando aplicável. Participação não deve condicionar notas da disciplina.

## Instrumentos e variáveis

Na coleta, o registro mais recente para um tópico deve ser determinado pela **sequência persistida dos eventos** (incluindo eventos `source=manual`), mesmo quando timestamps históricos estejam ausentes, empatados ou fora de ordem. Para análise de desempenho, filtrar somente `source=quiz` e preservar resultados e reprovações anteriores. Registrar separadamente conclusão manual, certificação por quiz e revisões heurísticas. Timestamps só devem fundamentar análises temporais após checagem de integridade e fuso. Esta política é requisito de qualidade dos dados, não resultado científico.

| Tipo | Variável / instrumento | Regra de coleta |
| --- | --- | --- |
| Primária | Nota em pós-teste externo ao JEW | Correção com gabarito previamente revisado, ajustada pela nota de pré-teste |
| Secundária | Retenção tardia | Avaliação equivalente, previamente revisada |
| Secundária | Tempo de estudo | Eventos ou diário com procedimento igual nos grupos |
| Secundária | Conclusões e revisões | Logs com definições documentadas, sem confundir marcação manual e certificação |
| Secundária | Usabilidade | Escala padronizada aplicada igualmente e entrevistas qualitativas opcionais |
| Processo | Falhas de IA, questões rejeitadas e `unverified` | Telemetria segura, sem texto pessoal ou segredos |

## Plano de análise prospectivo

Usar o desfecho primário pré-registrado e relatar diferença estimada, intervalo de confiança e tamanho de efeito, incluindo incerteza e dados faltantes. Uma análise possível é regressão/ANCOVA do pós-teste ajustando pelo pré-teste e variáveis definidas antes da coleta. Relatar adesão, desistências e análise de sensibilidade. Não inferir causalidade de comparação voluntária não randomizada. Dados sintéticos servem para ensaiar coleta e scripts, nunca para estimar efeito do JEW.

## Riscos e limitações

Aprendizagem pode depender de professor, motivação, dispositivo, conhecimento prévio e qualidade dos conteúdos gerados. A heurística de revisão do JEW usa intervalos fixos por sequência de aprovações e **não** é um modelo cognitivo validado. Um quiz aprovado prova apenas a execução da política de correção daquele quiz; não valida necessariamente seu conteúdo fora da gramática matemática implementada. Necessária revisão independente de itens antes do estudo.

## Condições para publicar conclusões

É preciso protocolo aprovado conforme a instituição, dados reais consentidos, instrumentos revisados, análise reproduzível e relatório de resultados positivos, nulos e negativos. Até lá, a afirmação defensável é que **o software implementa mecanismos auditáveis e testáveis**, com impacto educacional ainda não medido.
