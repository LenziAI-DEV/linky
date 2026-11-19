# Produção do MVP (16 a 20/11/2026)

> Plano aprovado por Felipe em 16/11/2026: **primeiro post automático na sex 20/11, às 18:30.** A aprovação por e-mail é a rede de segurança, porque nada sai sem o "aprovar" dele. Por isso não há semanas de sombra: o teste é o uso real, e as melhorias entram toda segunda com os números da semana.

## O fluxo em produção

```
coleta (cron, a cada 3h) ──► itens em ~/linky-dev/data/items (montados no serviço, só leitura)
07:00 seg a sex, dom 21:00  n8n linkyProposals ─► POST /curate ─► triagem + curadoria + pauta
                             (3 cards; 5 no domingo; lote = horário agendado, repetir não duplica)
                         └─► POST /proposal_email ─► e-mail de pautas (~07:05; Felipe escolhe e opina)
:05, :20, :35, :50  n8n linkyApprovalEmails ─► POST /draft_next ─► redação + checagem + arte + motor
                                          └─► POST /approval_emails ─► e-mail de aprovação
                                              (Felipe escolhe o hook e a leitura, aprova ou pede ajuste)
18:30 seg a sex  n8n linkyPublish ─► GET /due ─► GET /images/{nome} ─► LinkedIn
                                 └─► published / failed (alerta) ; em sombra, só o e-mail "Publicaria agora"
```

## Frentes (cada uma numa sessão com worktree própria)

| Frente | Entrega | Arquivos |
|---|---|---|
| **Pautas** | Agentes de triagem e curadoria; `curate()` | `src/linky_agents/agents/pautas.py`, `prompts/triagem/v1.md`, `prompts/curadoria/v1.md`, testes |
| **Post** | Agentes de redação e checagem; `fetch_sources()`, `write()`, `compose()` | `src/linky_agents/agents/post.py`, `prompts/redacao/v1.md`, `prompts/checagem/v1.md`, testes |
| **Imagem** | Agente de arte; `make_image()`; o motor rodando dentro do serviço | `src/linky_agents/agents/art.py`, `prompts/arte/v1.md`, `ops/linky/Dockerfile` (fontes e assets), testes |
| **Orquestração** (sessão principal) | Rotas `/curate`, `/draft_next`, `/images/{nome}`; escolha do hook e da leitura no formulário de aprovação; ajuste refaz o post; workflows do n8n; deploy | `src/linky_agents/service/`, `n8n/`, `ops/linky/compose.yaml` |

**Contratos:** `src/linky_agents/agents/contracts.py`. Assinaturas, tipos e o que o serviço espera de cada módulo estão lá. Mudar um contrato é combinar com a sessão principal antes.

## Regras para as frentes

- **Fontes das regras editoriais:** `docs/editorial/voz.md` (fixo), `docs/editorial/playbook.md` (padrões, hooks, estruturas, fechamento, lista de cortes) e `docs/editorial/rubrica.md`. A rubrica v1 vale com as sugestões das 8 perguntas, decididas pelo padrão em 16/11.
- **Modelos:** `config/models.yaml`. A redação passa a começar no `claude-sonnet-5-5`; a DeepSeek fica fora da redação (D19). A frente Post ajusta a cadeia.
- **Prompts:** `prompts/<agente>/v1.md`, nas regras de `prompts/README.md`. A parte fixa vai primeiro, por causa do cache.
- **Testes offline** com o `FakeProvider` do harness, sem rede. `uv run python -m pytest` e `uv run ruff check src tests` precisam passar.
- **Avaliação com modelo de verdade só na VPS**, porque as chaves estão só lá (`/opt/linky/.env`):
  - imagem de teste da worktree: `docker build -f ops/linky/Dockerfile -t linky-agents:<frente> .`, numa pasta própria em `~/`;
  - `docker run --rm --env-file /opt/linky/.env -v linky_<frente>_teste:/data ...`;
  - **nunca** com `--network` nem `--network-alias`, **nunca** com o volume `linky_data` e **nunca** rodando o `deploy.sh`;
  - **gasto máximo de US$ 0,50 por frente** em avaliação, medido pelo ledger do volume de teste;
  - no fim, apagar o volume e a imagem de teste.
- **Material de avaliação:** o gold set (`eval/gold/`, dias 06, 09 e 10/11, com as escolhas de Felipe e os posts aprovados) e os itens coletados (`~/linky-dev/data/items/`).
- **Entrega:** commits na própria branch. Com os testes verdes, avisar a sessão principal (SendMessage) com o resumo, o custo por execução medido e o que ficou de fora. **A sessão principal faz o merge e o deploy** (autorizada por Felipe). Prazo: **qua 18/11 à noite**.

## Calendário

| Dia | O quê |
|---|---|
| Seg 16 (noite) | Contratos na `main`; frentes abertas; Felipe grava as chaves de API e a do n8n na VPS |
| Ter 17 e qua 18 | Frentes em paralelo; orquestração na sessão principal |
| Seg 16 (noite) | ✅ As 4 frentes mescladas na `main`; revisão completa e correções (abaixo); **deploy antecipado** (~23:40 UTC); ensaio real e upload ao LinkedIn testados; **modo sombra desligado** em 17/11 00:06 UTC, a pedido de Felipe |
| **Ter 17** | **Primeiro e-mail real de pautas (07:00) e primeiro post automático (18:30, se aprovado)**. As linhas de qua 18 a sex 20 abaixo eram o plano original, já cumprido |
| **Qua 18 (noite)** | **Deploy** (antes das 07:00 de quinta, senão não há e-mail real): `git pull` na VPS, `deploy.sh`, reimportar `linkyProposals`, `linkyApprovalEmails` e `linkyPublish` (seg a sex), ativá-los pela API do n8n, conferir `docker ps` e o teto diário de gasto |
| Qui 19 | Ensaio real: e-mail das 07:00 de verdade, Felipe escolhe, o post chega para aprovar; às 18:30 a publicação em sombra manda o e-mail "Publicaria agora". **Go/no-go às 12:00:** e-mail de pautas com 3 novas e um post com imagem chegou para aprovar |
| Sex 20 | Conferir no e-mail de sombra de quinta que legenda e imagem são as aprovadas; **sair do modo sombra até 16:30** (`LINKY_SHADOW=0` + deploy); **18:30: primeiro post automático** |
| Toda segunda | Ciclo de melhoria: números da semana → ajustes de prompt e playbook → deploy |

**Contingência da sexta:** se a esteira falhar, publicar pelo `ops/publish-once.sh` (o caminho do T2) com texto e imagem que Felipe aprovou, ou não publicar. Sem aprovação, nada sai.

## Revisão de 16/11 (antes do deploy)

Cinco revisões em paralelo:
- padrões de código;
- spec;
- simulação de uma semana inteira com os horários reais do n8n;
- segurança;
- arquitetura.

Depois, uma dupla checagem de arquiteto e gestor sobre todas elas.

**Segurança:** nenhuma falha explorável.

**Corrigido em 16/11 (`20546b9`, 482 testes):**
1. **Bloqueava o lançamento:** nos dias úteis, a curadoria das 07:00 não trazia pautas novas, porque a janela se ancorava no relógio e não no horário agendado. Agora o lote, a janela e as pautas novas saem do horário agendado do envio.
2. A legenda escolhida no formulário só é gravada junto com a aprovação. Se a aprovação é recusada, nada muda.
3. Roda uma redação por vez: uma chamada concorrente volta sem fazer nada, e uma imagem já mostrada a Felipe nunca é sobrescrita.
4. Depois de 2 falhas da redação, a pauta volta ao banco e libera o horário, com uma mensagem que diz o que fazer.
5. Curadoria sem itens gera alerta (é o sinal de coleta parada).
6. O e-mail de sombra mostra a hora de Brasília.
7. No n8n, a redação passa a rodar em :05/:20/:35/:50 (não cai junto com a curadoria), e a curadoria tem 600 s de limite.

O backlog que saiu desta revisão está em [Backlog](#backlog-lista-única), no fim do arquivo.

## Incidente de 17/11 (primeiro dia em produção)

- **O que houve:** o e-mail de pautas das 07:00 não saiu; às 07:10 veio o alerta "Esteira com falha" (triagem: nenhum modelo da cadeia entregou saída válida). Nenhum custo, nada publicado.
- **Causa:** o `linky-agents` estava só na rede `n8n_n8n-internal`, que é `internal: true` (sem gateway, sem DNS externo). As 4 chamadas da triagem deram `ConnectError` em ~3 ms nos 3 modelos da cadeia. O ensaio de 16/11 passou porque rodou num container descartável em outra rede: o container de produção nunca tinha saído para a internet.
- **Correção (`2d1be62` e seguinte):** rede `linky_egress` no compose; `ops/linky/check-egress.sh` no `deploy.sh` e no `shadow.sh`; teste de contrato `tests/test_ops_linky.py`; `deploy.sh` lido inteiro antes de rodar (o `git pull` reescrevia o script no meio e a checagem nova não rodou no primeiro deploy).main`.
- **Recuperação:** no ar às 16:25 UTC; curadoria refeita (87 fatos, 3 pautas, US$ 0,008) e e-mail de pautas reenviado às 16:28 UTC (13:28 BRT). O e-mail caiu na aba Atualizações do Gmail, não na Principal.
- **Lições:** (1) ensaio tem que rodar no container de produção, não numa cópia; (2) healthy não prova que os agentes funcionam: o deploy agora confere a saída; (3) o n8n marca a execução como sucesso quando o `/curate` dá 502 (`neverError`): o alerta por e-mail é o único sinal, e funcionou.

## Backlog (lista única)

> Tudo o que ficou para depois do lançamento: o que se achou nas revisões, nas calibrações e no uso. **Item novo entra aqui**, mesmo que o detalhe fique em outro arquivo (aí vai o link). Atualizada em 18/11/2026.

### 1. Ciclo de segunda (23/11), em ordem

1. **Registro do playbook §8:** tipo do hook, estrutura, fechamento e qual hook e leitura Felipe escolheu. Sem isso, o aprendizado não tem dados; a semana 1 pode ser reconstruída do registro do harness.
2. **`recent_hooks`:** tirar o próprio post em ajuste, os descartados e os vencidos.
3. **Formulário:** Felipe poder reescrever o hook em texto livre.
4. **Arte no ajuste:** o pedido de ajuste chegar à arte.
5. **Exclusão de pautas:** por fato ou URL, e não por título.
6. **Teste ponta a ponta:** App + `RealAgents` + `FakeProvider`, com o nome do registro da arte num lugar só.
7. **"Próximo horário livre":** o formulário não oferecer a opção quando não há horário válido.
8. ✅ **SSRF em `fetch_sources`** (19/11): `linky_agents.netguard.check_url` antes de cada requisição e de cada redirecionamento (seguidos à mão, até 5). Só http/https nas portas 80/443, sem usuário na URL, sem nome de serviço Docker nem `localhost`, e todo IP resolvido tem que ser público (bloqueia privado, loopback, link-local/metadata, CGNAT, IPv4 mapeado). Risco residual: DNS rebinding entre a checagem e a conexão (docstring do módulo).
9. **Contrato:** `post.compose` vs `pipeline.recompose`, uma regra só.
10. **Prompts:** tirar as notícias reais dos exemplos (`prompts/README.md`).
11. **Qualidade das pautas:** só 3 de 8 escolhas de Felipe no top 3 do gold set; ver `docs/editorial/calibracao/03-curadoria-v1.md`.
12. **Arte recusada pelo motor (17/11):** na pauta "Califórnia processa OpenAI" (`2026-11-16-1738f67eaaddba29`), a 1ª tentativa (17:35 UTC) teve as 3 propostas do agente de arte recusadas, todas no "diagrama de passagem". Os motivos foram `[margem]`: a nota ocupava x 3..1005, fora da margem de 72 px. E `[colisão]`: as legendas do centro ficavam metade dentro, metade fora da borda. A 2ª tentativa (17:50) passou. O agente não está respeitando a área útil nem as bordas dos blocos com rótulo. Fazer duas coisas. (a) O prompt ou os exemplos da arte devem deixar explícitas a margem e a regra "legenda dentro ou fora do bloco, nunca na borda". (b) O motor deve devolver os motivos da recusa ao agente para a próxima proposta, se isso ainda não acontece. Medir quantas propostas são recusadas por post no registro do harness. Hoje a falha só aparece quando as 3 são recusadas; o alerta de falha já resolvida foi retirado em `1704587`.
13. **Manchete da arte:** o ponto final depois da palavra destacada sai separado ("LICENÇA ."). Visto no post de 17/11.
14. **Repo público ([LenziAI-DEV/linky](https://github.com/LenziAI-DEV/linky), desde 19/11):** depois do deploy, atualizar o retrato público com `tools/public/export_public.py` (passo a passo na docstring). Dado sensível novo (domínio, e-mail, host, ID de credencial) entra em variável de ambiente ou na lista `SUBSTITUIR`; o script falha se sobrar algo da lista `PROIBIDOS`.

### 2. Também para os ciclos de segunda, por frente (sem ordem)

**Pautas** ([03-curadoria-v1.md](../editorial/calibracao/03-curadoria-v1.md), "Próximos passos"; ligado ao item 11):
- Decidir com Felipe um critério de **tamanho do fato** (fontes independentes, repercussão no Brasil) ou subir o peso de Brasil.
- Curadoria numa chamada só nos lotes grandes (`CURATION_BATCH` 60), para notas comparáveis no domingo.
- Agrupamento por fato (ADR 0007): o IPO de 10/11 veio em 4 fatos; o `same_as` junta pouco.
- Medir pela escolha real de Felipe a partir de 19/11 (a avaliação no gold set é otimista).

**Redação** ([03-redator-v1.md](../editorial/calibracao/03-redator-v1.md), "Leitura crítica", pontos 2 a 5):
- Hooks que repetem a fórmula do exemplo do playbook ou são clichê.
- Detalhe lateral sobrando no corpo ("uma ideia por post").
- Tiques vindos do exemplo do prompt ("Sim ou ainda não?", "Uma ressalva:"): o prompt mudou, mas não foi medido de novo.
- Lista com rótulo em cada item escapa da validação.
- A voz pessoal depende da linha de opinião no e-mail de pautas: ver se Felipe está mandando e se dá para incentivar.

**Arte** ([03-arte-v1.md](../editorial/calibracao/03-arte-v1.md), "Para a v2"; ligado ao item 12):
- Legenda só para cor ou forma que aparece no esquema.
- Não repetir no esquema o número que a manchete já diz.
- `source_note` só para ressalva sobre o fato, nunca sobre o desenho.
- Mais metáforas da própria notícia (um 3º exemplo no prompt, sem número).
- Logos oficiais das empresas no topo (hoje só o nome em Barlow Bold).

### 3. Funcionalidades fora do MVP (entram com o uso)

- **Post sob demanda por e-mail:** desenhado, a construir ([ADR 0008](../adr/0008-post-sob-demanda.md), CONTINUIDADE §4.9). Precisa de MX e recebimento no Resend.
- **Relatório mensal e mudança automática do playbook:** fim da semana 4 do laboratório editorial (~13/12). Até lá, quem ajusta o playbook é a sessão de segunda.
- **Base de referências pelo Apify** (laboratório editorial).
- **Várias imagens por post.**
- **Válvula criativa da arte** (SVG livre com revisão, ADR 0002/0006): só se a composição por peças ficar limitada.

### 4. Dívida técnica (sem pressa)

- Extrair a esteira de `app.py`.
- `Post.caption()`.
- `draft_failures.json` como evento da fila.
- `Card` vs `CardOut`.
- Os alertas como enum.
- A rota `/agents` (morta em produção).
- O fuso fixo em `pautas.py`.
- Agrupamento com embeddings, só se a triagem medir que vale (ADR 0007).
