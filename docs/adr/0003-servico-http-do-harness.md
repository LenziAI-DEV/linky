# ADR 0003: serviço HTTP do harness com a biblioteca padrão, em container separado do n8n

- **Status:** aceita · **Data:** 07/11/2026 · **Decisores:** Claude (arquitetura), a partir da D17 e da D14 decididas com Felipe

## Contexto

A D17 separa os papéis: o n8n orquestra (relógios, e-mails, publicação) e o harness próprio decide (fila editorial, agentes, custo). A fila (ADR 0001) e o harness (etapa A) existiam só como biblioteca Python, e o n8n precisa chamá-los. Restrições:

- **Memória:** a VPS `vps` tem 2 GB e roda produção (n8n com fluxos de outro projeto, ~440 MiB; Postgres; Traefik; `outro-servico`). O serviço tem teto de 256 MB.
- **Isolamento:** não pode tocar no compose do n8n (`/opt/n8n`) nem reiniciar o que já roda.
- **Exposição:** só o n8n chama. Nada na internet.
- **Sem chaves de API por enquanto:** a fila não usa LLM e precisa funcionar sem elas.
- **E-mail:** pela D14, só o n8n envia (Resend). O harness nunca tem a chave.
- **Volume:** poucas chamadas por hora (relógio de hora em hora, 3 envios de pauta por dia útil, 3 publicações por semana).

## Decisão

1. **Servidor HTTP da biblioteca padrão** (`http.server.ThreadingHTTPServer`), sem dependência nova. A lógica fica em `App.handle(método, caminho, cabeçalhos, corpo) -> (status, JSON)`, que não conhece sockets. O adaptador (`server.py`) só traduz a conexão. Os testes exercitam rotas, autenticação, erros, fila e ledger pela mesma interface que o n8n usa, sem rede. Um teste de fumaça cobre o socket.
2. **Rotas** com os mesmos nomes do domínio:

   | Método e caminho | O que faz |
   |---|---|
   | `GET /health` | Saúde. A única rota sem segredo; não devolve dados |
   | `POST /propose` | Registra um lote de pautas (`batch` + `entries`) |
   | `POST /entries/{id}/{choose,bank,discard,drafted,approve,reschedule,published,failed}` | Transições da fila. `choose`, `approve` e `reschedule` aceitam `when` (data) |
   | `POST /batches/{lote}/none_today` | "Nenhuma hoje" |
   | `GET /entries/{id}` | Uma pauta |
   | `POST /tick` · `GET /due` · `GET /proposal_plan` · `GET /agenda?n=` · `GET /inbox?limit=` | Relógio, publicação e leitura |
   | `GET /alerts` · `POST /alerts/ack` | Alertas do ledger pendentes e confirmação de leitura |
   | `GET /spending` | Gasto do dia e do mês e os tetos |
   | `GET /linkedin/token` · `POST /linkedin/token` | Validade do token do LinkedIn (`expires_on`), registrada ao reconectar a credencial (etapa E) |
   | `POST /agents/{nome}` | Execução de um agente registrado (vazio até os prompts finais, depois do T2) |
   | `POST /curate` | **Esteira (16/11):** itens da coleta → triagem, curadoria e pauta → lote do horário agendado (`AAAA-MM-DD-HHMM`). Repetir no mesmo horário não duplica. Sem itens na janela: alerta "Esteira com falha" |
   | `POST /draft_next` | **Esteira:** uma pauta escolhida (ou com ajuste pedido) por chamada → redação, checagem e arte → post aguardando aprovação. Uma execução por vez (chamada concorrente volta sem fazer nada); 2 falhas na mesma escolha devolvem a pauta ao banco e liberam o horário |
   | `GET /images/{nome}` | **Esteira:** a imagem do post em base64, para o e-mail de aprovação e a publicação. Uma imagem gravada nunca é sobrescrita |

   Erros: 401 sem segredo, 404 pauta, lote, agente ou rota inexistente, 405 método errado, 409 regra da fila violada (estado errado, horário ocupado, pauta vencida, lote repetido), 422 corpo fora do contrato, 400 JSON inválido, 402 teto de custo, 502 nenhum modelo entregou saída válida (na `/curate`, qualquer falha dos agentes; a `/draft_next` responde 200 com `failed` e avisa por alerta).
3. **Segredo compartilhado** no cabeçalho `X-Linky-Token`, comparado em tempo constante, mesmo dentro da rede interna. Vem de `LINKY_SERVICE_TOKEN` (em `/opt/linky/.env`, modo 600). Sem segredo, o serviço não sobe.
4. **Alertas como caixa de saída com confirmação.** O gancho de alerta do harness grava em `alerts.db`; o n8n lê `GET /alerts`, envia o e-mail e confirma com `POST /alerts/ack`. Ler não consome: se o envio falhar, o alerta continua pendente. O harness segue sem saber de e-mail.
5. **Chamadas repetidas não reabrem pautas.** `propose` recusa (409) um lote já registrado ou uma pauta que já está na fila. Antes, um lote repetido pelo n8n podia devolver uma pauta escolhida ao estado "proposta".
6. **Concorrência simples.** Cada operação da fila abre a conexão SQLite, trabalha e fecha, sob uma trava. Execuções de agente usam outra trava, uma por vez, para o teto de custo ver o gasto real.
7. **Container separado:** imagem `python:3.12-slim` em dois estágios (o uv só no build), usuário sem privilégio, sistema de arquivos só leitura, `cap_drop: ALL`. Compose próprio em `/opt/linky/compose.yaml`, limite de 256 MB sem swap extra, 0,5 CPU. **Sem porta publicada e sem rota no Traefik.** Duas redes: `n8n_n8n-internal` (entrada: o n8n chama `http://linky-agents:8080`) e `linky_egress`, uma bridge só deste serviço (saída: APIs dos modelos e texto das fontes). A rede do n8n é `internal: true` e não sai para a internet (incidente de 17/11/2026, abaixo).
8. **Dados num volume** (`linky_data` em `/data`): os bancos SQLite `editorial.db` e `alerts.db`, e os arquivos JSONL do ledger (`ledger/`) e de registro (`runs/`). Backup diário por snapshot feito de dentro do container com a API de backup do SQLite (consistente mesmo com o serviço gravando), num script próprio (`/opt/scripts/backup-linky.sh`), sem mexer no `backup-n8n.sh`.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| **FastAPI + Uvicorn** | Validação e OpenAPI de graça, mas acrescenta FastAPI, Starlette, Uvicorn, anyio e dependências (~10 pacotes) e ~15 a 25 MiB de memória ociosa a mais, para um serviço com uma dúzia de rotas e poucas chamadas por hora. A validação já é feita pelo Pydantic, que o projeto usa. O ganho (documentação automática) não paga o custo num serviço só interno |
| **Starlette + Uvicorn** | Mais leve que o FastAPI, mas ainda traz um servidor ASGI e assíncrono para código todo síncrono (SQLite e `httpx` síncronos). Assíncrono só complicaria |
| **Rodar o harness pelo n8n via `docker exec` ou SSH** | O n8n teria acesso ao socket do Docker ou a uma chave SSH da VPS: privilégio demais para o container mais exposto da máquina |
| **Expor pelo Traefik com autenticação** | Abre uma superfície na internet sem necessidade. Só o n8n chama, e ele está na mesma rede Docker |
| **Rede Docker própria, ligando o n8n a ela** | Exigiria `docker network connect` no container do n8n (mudança fora do compose dele, perdida ao recriar) ou editar o compose do n8n, que está fora do escopo |
| **Fila de alertas em memória ou empurrada para um webhook do n8n** | Em memória, um reinício perde alertas. Empurrar exige o harness saber do n8n e tratar a falha de entrega. A caixa com confirmação é durável e mantém o harness agnóstico de transporte |

## Consequências

- **Positivas:** nenhuma dependência nova; memória medida (T8, 07/11/2026): **~28 MiB ocioso**, **30 MiB** sob 2.640 leituras concorrentes (8 threads, todas 200, p50 de 29 ms) e **45 MiB** de pico num container de teste com 1.000 pautas na fila e 1.400 escritas concorrentes. É menos de 20% do limite de 256 MB. As regras seguem testadas pela mesma interface que o n8n usa.
- **Negativas:** sem documentação OpenAPI automática (a tabela acima e os testes fazem esse papel). O `http.server` não é um servidor para internet: aceitável porque nada fora da rede interna o alcança. A fila lê todas as entradas a cada operação: com 1.000 pautas a latência sobe para centenas de milissegundos; no volume real (dezenas por mês) não importa, mas um arquivamento será preciso se a fila crescer muito.
- **Incidente de 17/11/2026 (revisão desta decisão):** com o container só na `n8n_n8n-internal`, que não tem gateway, toda chamada aos modelos falhou no DNS e a curadoria das 07:00 não saiu. Até 16/11 o serviço não chamava modelos, e o ensaio real rodou num container descartável em outra rede, por isso ninguém viu. Correção: a rede `linky_egress` no compose e `ops/linky/check-egress.sh`, rodado pelo `deploy.sh` e pelo `shadow.sh` depois de recriar o container (healthy não basta). O container passa a ter saída livre para a internet, necessária para baixar as fontes dos posts; entrada continua fechada.
- **A rede `n8n_n8n-internal` também tem o Postgres do n8n.** O serviço não tem credenciais dele; o risco é aceito para não mexer no compose do n8n.
- **Eventos do `tick`** vêm na resposta, não numa caixa como os alertas: se o n8n falhar depois de chamar o `tick`, o evento se perde (a mudança de estado da fila, não). A decidir na etapa C, se for problema na prática.
