# JEW Ultimate — estado da evolução

Atualizado em 26/10/2026. Este documento distingue implementação de validação. A plataforma completa descrita no pedido ainda está em desenvolvimento.

## Entregue nesta etapa

- O roadmap 2D usa cartões retangulares com títulos internos, estados visuais, conexões ancoradas nas bordas, seleção e arraste pela área do cartão. Posições manuais continuam no formato existente. O modo 3D permanece disponível.
- O roadmap abre com o chat e a árvore lateral recolhidos em perfis sem preferência anterior. Preferências antigas são respeitadas. Há controles de zoom, ajuste à janela e atalhos `+`, `-`, setas e `F`.
- O onboarding aparece no primeiro snapshot de um perfil novo, inclusive quando existe o grafo de demonstração. Após salvar, o perfil permanece no SQLite e a entrada posterior abre diretamente o workspace. Bases existentes com snapshots anteriores não são forçadas a refazer o onboarding.
- O perfil inclui horas de estudo semanais e preferências de aprendizagem. Esses dados são enviados como contexto para a geração de roadmap. A edição fica em Configurações.
- O modal de onboarding e criação de roadmap usa uma paleta escura de superfícies neutras, texto claro e mostarda, com adaptação ao tema claro.
- Foi criado o repositório público `deeeeniiiq/Jew`; o remoto do projeto original continua separado.

## Evidências

- Frontend: 179 testes em 31 arquivos; verificação de tipos, localização e build de produção aprovados.
- Backend: 294 testes aprovados, incluindo persistência do perfil após reabrir o repositório SQLite.
- Desktop: 22 testes aprovados antes das alterações de perfil; nenhuma distribuição Windows foi empacotada nesta etapa.
- Capturas com backend e banco temporários: [onboarding novo](validation/jew-onboarding.png) e [workspace com roadmap 2D](validation/jew-roadmap-2d.png). São verificações visuais em 1280 × 900, não substituem testes de interação no desktop.

## Verificação parcial

- Os testes cobrem geometria dos cartões, enquadramento e persistência do perfil. Seleção, arraste, pinça, tela cheia, atalhos e gravação das posições após reinício ainda precisam de uma sessão de teste manual completa no aplicativo distribuído.
- A visualização 3D foi preservada no código e o build passou; não foi comparada visualmente nesta etapa.
- O fluxo existente gera prévias estruturadas e apresenta fontes identificadas. A pesquisa profunda, comparação de fontes e verificação de cada referência ainda não atendem ao objetivo proposto.

## Pendências por prioridade

| Prioridade | Entrega | Dependência | Manutenção | Benefício |
| --- | --- | --- | --- | --- |
| Alta | Pesquisa profunda com evidências, comparação e cancelamento | Contrato de fontes e adaptadores de busca | Alta | Evita trilhas inventadas |
| Alta | Edição de nós, vínculos e notas com autosave e desfazer/refazer | Modelo persistente e histórico de operações | Alta | Faz do roadmap um espaço de trabalho real |
| Alta | Testes funcionais desktop e revisão de acessibilidade do Canvas | Ambiente Windows de validação | Média | Confiança nas interações centrais |
| Média | Chats contextuais independentes por tópico | Persistência e controle de contexto | Média | Ajuda diretamente durante o estudo |
| Média | Desafios, evidência de competência e Projetos possíveis | Critérios objetivos e registro de tentativas | Alta | Mede aplicação do conhecimento |
| Média | PDF de tópicos, notas, projetos e roadmap | Pipeline de composição e paginação | Média | Permite compartilhar material legível |
| Média | Imagens seguras em notas e questões | Armazenamento validado e limites de arquivo | Alta | Amplia áreas de estudo |
| Baixa | Comparação de versões, favoritos, busca global e indicadores de atualização | Contratos acima estabilizados | Média | Melhora navegação e manutenção |

Nenhuma das pendências acima deve ser apresentada como concluída apenas por existir um botão, uma prévia ou um teste unitário.
