# ADR 0010: repositório público como retrato higienizado do privado

- **Status:** aceita · **Data:** 19/11/2026 · **Decisores:** Felipe (produto e exposição) e Claude (segurança e mecânica)

## Contexto

O linky também é um case de portfólio (PRD, fase 3 "Publicar o case"; D6 e D15 do briefing). Com o MVP em produção desde 17/11, Felipe quis mostrar o projeto a recrutadores, com rigor sobre segredos, dados pessoais e vulnerabilidades.

Auditoria de 19/11 no `linky-dev` (gitleaks no histórico inteiro e na árvore, trivy, varredura manual das linhas adicionadas em todos os commits):

- **Nenhum segredo real**, nem no histórico. O único achado do gitleaks é uma chave falsa num teste (`tests/test_harness_providers.py`).
- **O histórico tem dados de infraestrutura e pessoais:** o IP e o ID da VPS, o usuário SSH e as regras de sudo, IDs de credenciais do n8n, o e-mail pessoal de Felipe (que é também o único remetente autorizado do post sob demanda, ADR 0008), o endereço que recebe pedidos, a URL do perfil dele e menções aos outros sistemas que dividem a VPS.
- **Uma falha conhecida e não corrigida estava no backlog:** SSRF em `fetch_sources`. Publicar o backlog seria divulgar a falha, então ela foi corrigida antes (`10f137b`, `linky_agents.netguard`).
- **O coletor de métricas** (ADR 0009) depende da conta pessoal de Felipe no LinkedIn e não acrescenta nada a quem lê o código. Os motivos completos estão no ADR 0009, que fica no privado.

## Decisão

1. **Repositório novo, `LenziAI-DEV/linky`, público, sem o histórico do privado.** O `linky-dev` continua privado: é a fonte do desenvolvimento e é dele que a VPS faz o deploy (deploy key só leitura). O público começa com um commit e recebe um commit por atualização.
2. **O retrato é gerado por script:** `tools/public/export_public.py`, que fica só no privado. Ele:
   - exporta só os arquivos versionados no `HEAD` (`git archive`), então `.env`, `data/`, `.claude/` e `.venv/` nunca entram;
   - remove a lista `EXCLUIR`: `docs/CONTINUIDADE.md`, `ops/README.md` (runbooks com infraestrutura e acessos), o briefing de descoberta (pessoal), o laboratório editorial, as execuções pontuais do T2/T3 e todo o coletor de métricas (código, testes, scripts e ADR 0009);
   - troca os identificadores de `SUBSTITUIR` (e-mails e domínios por `example.com`, o host SSH por `vps`, IDs de credencial por marcadores, nomes de terceiros por "outro projeto");
   - transforma em texto simples os links para arquivos excluídos;
   - troca o `README.md` pelo `tools/public/README.public.md` (voltado a recrutador) e grava o `.gitleaksignore` da chave falsa;
   - corta do público as linhas e seções que descrevem o coletor de métricas (`CORTAR_LINHAS` e `CORTAR_SECOES`);
   - **falha** se qualquer padrão de `PROIBIDOS` sobrar em qualquer arquivo.
3. **Antes de cada push:** `uv lock`, `pytest`, `ruff`, `gitleaks git` no clone público e conferência da página sem login. O commit sai com o e-mail noreply do GitHub, não com o pessoal.
4. **O que vai a público por inteiro (decisão de Felipe, 19/11):** código, testes, prompts, ADRs, PRD, `voz.md`, playbook, rubrica, calibrações e gold set. A D6 previa um `voz.md` resumido, mas Felipe preferiu mostrar o método inteiro: a voz depende dos prompts, da calibração e do uso, e não só do texto. O gold set fica porque só tem notícias públicas e as escolhas editoriais dele.
5. **Sem licença.** Todos os direitos reservados, como nos outros repositórios do perfil.
6. **Quando atualizar:** depois do deploy do ciclo de segunda (backlog, item 14), com o passo a passo da docstring do script. O push no público é publicação e precisa do OK de Felipe.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Tornar o `linky-dev` público como está | O histórico expõe a infraestrutura da VPS, que roda também outro sistema em produção |
| Reescrever o histórico (`git filter-repo`) e abrir o `linky-dev` | Mexe no repositório de onde a VPS faz o deploy, e cada dado sensível teria de ser pego em 100+ commits. Um erro deixa o dado público para sempre |
| Espelho automático (GitHub Action a cada push) | Publica sem revisão humana e exigiria um token com escrita no repo público guardado no privado. O volume (um retrato por semana) não justifica |
| Publicar o coletor de métricas | Atrelado à conta pessoal de Felipe (ADR 0009) |

## Consequências

- **Positivas:** os recrutadores veem o código real de produção, com testes e CI verdes. O histórico privado continua intacto. A higienização é repetível e falha de forma segura (padrão proibido = sem retrato).
- **Negativas:** o público não mostra a evolução commit a commit. Dado sensível novo precisa entrar na lista `SUBSTITUIR` (ou, melhor, em variável de ambiente). Os links e as menções a arquivos excluídos (`CONTINUIDADE`, `ops/README.md`) aparecem como texto sem destino.
- **Regra para código novo:** domínio, e-mail, host, ID de credencial e caminho da VPS vão para variável de ambiente ou configuração, não para o código. Se aparecerem num arquivo versionado, entram na lista `SUBSTITUIR` no mesmo commit.
