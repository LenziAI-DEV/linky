# ADR 0004: workflows da fila no n8n, e-mails redigidos no harness e modo sombra no serviço

- **Status:** aceita · **Data:** 07/11/2026 · **Decisores:** Claude (arquitetura), dentro das regras de Felipe (aprovação explícita, publicação só seg, qua e sex às 18:30)

## Contexto

A etapa C liga a fila editorial (ADR 0001), já exposta pelo serviço `linky-agents` (ADR 0003), aos relógios do n8n: o relógio de hora em hora, a publicação nos horários fixos e a entrega dos alertas de custo. Restrições:

- **T2 em andamento até ~13/11:** a semana Mágico de Oz publica à mão (`ops/publish-once.sh`). Nada desta etapa pode publicar no LinkedIn nem disputar esses disparos. Tudo roda em **modo sombra** até o fim do T2.
- **n8n de produção compartilhado com outro projeto:** sem reiniciar o n8n. Ativar workflows agendados pelo CLI exige reinício; eles ficam importados e **inativos** até Felipe ativá-los pela interface.
- **A fila não guardava o post.** Para publicar sem um workflow por post (como no T2), a pauta precisa levar legenda, texto alternativo e imagem.
- **Formato *little* do LinkedIn:** `| { } @ [ ] ( ) < > # \ * _ ~` precisam de escape (T3).

## Decisão

1. **O post entra na fila no `drafted`.** A rota `POST /entries/{id}/drafted` passa a exigir `{commentary, alt_text, image}` (a imagem é só o nome do arquivo em `/home/node/.n8n-files/linky/`). Na fila (`Queue.drafted`) o post é opcional, para os testes de calendário não precisarem dele; a regra que importa fica no `approve`, que recusa (409) pauta sem post: Felipe sempre aprova o conteúdo exato. O texto é guardado **sem escape**, como Felipe aprova; o limite de 3.000 caracteres do LinkedIn é conferido **depois** do escape, já no `drafted` (422).
2. **O escape do *little* fica no harness** (`linky_agents.little.escape_little`, com teste), aplicado só na saída: `GET /due` devolve `linkedin: {commentary (já escapada), alt_text, image_path}`, o post no formato do LinkedIn. `#` seguido de letra fica sem escape (hashtag clicável, como no T3).
3. **Novo estado "em publicação"** (`POST /entries/{id}/publishing`, de aprovada para em publicação). O workflow marca o post antes de chamar o LinkedIn; o post sai do `due`, e uma execução repetida ou concorrente não publica duas vezes. `published` e `failed` aceitam aprovada ou em publicação. Um post que fica preso em publicação (o n8n caiu no meio) não é reenviado: é revisado à mão.
4. **E-mails redigidos no harness, transportados pelo n8n.** As respostas trazem o e-mail pronto (`{subject, html, text}`) ou `null`: `POST /tick` (eventos que pedem ação: lembrete, adiamento, vencimento e revalidação, num só e-mail por passagem do relógio), `GET /alerts` e, em sombra, cada item do `GET /due`. O n8n só chama o Resend. Títulos vindos da web são escapados no HTML. A antecipação (`pulled_forward`) não gera e-mail: não pede ação e aparece na agenda do e-mail de pautas.
5. **Modo sombra é uma configuração do serviço:** `LINKY_SHADOW` em `/opt/linky/.env`, **ligado por padrão**. Só `off`, `false` ou `0` desligam; valor desconhecido impede o serviço de subir. Em sombra, todo assunto ganha `[sombra]`, e o `GET /due` diz `shadow: true` e traz o e-mail "Publicaria agora". O workflow de publicação só segue para o LinkedIn se a resposta disser **`shadow === false`** explicitamente; qualquer outra coisa (campo ausente, serviço antigo) cai no ramo sombra, que só manda o e-mail. Em sombra, nada muda na fila.
6. **Três workflows genéricos**, inativos, com gatilho agendado e gatilho manual (o CLI executa pelo agendado), fuso `America/Sao_Paulo`:

   | ID | Nome | Gatilho | Fluxo |
   |---|---|---|---|
   | `linkyQueueClock` | `[linky] Fila - relógio (tick de hora em hora)` | `0 * * * *` | `POST /tick` → e-mail (se houver) |
   | `linkyLedgerAlerts` | `[linky] Alertas do ledger (de hora em hora)` | `10 * * * *` | `GET /alerts` → e-mail → `POST /alerts/ack` |
   | `linkyPublish` | `[linky] Publicação (seg, qua e sex, 18:30)` | `30 18 * * 1,3,5` | `GET /due` → 1 post (o de horário mais antigo) → **confere a imagem antes de tudo** → sombra: manda o e-mail; real: em publicação → fluxo do T3 (userinfo, upload, `/rest/posts`) → `published` com o URN do cabeçalho `x-restli-id` (sem o cabeçalho, grava um aviso no lugar do URN em vez de deixar o post preso), ou `failed` com o erro de qualquer nó do LinkedIn. Imagem ausente: em sombra, o e-mail sai com "IMAGEM NÃO ENCONTRADA" no assunto; fora da sombra, `failed` antes de tocar no LinkedIn. Nunca reenvia |

7. **Credencial `linky-agents (X-Linky-Token)`** (Header Auth, ID `linkyAgentsToken`), restrita ao domínio `linky-agents`, criada por `n8n import:credentials` na VPS com o valor lido de `/opt/linky/.env`, sem passar pelo repositório nem pelo terminal.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Flag de sombra num nó Set de cada workflow | Três lugares para virar, e esquecer um deles publica. A configuração do serviço é uma só e vale para tudo |
| Variáveis do n8n (`$vars`) ou variável de ambiente do n8n | `$vars` é recurso pago; variável de ambiente exige reiniciar o n8n de produção |
| Escape e e-mails em nós Code do n8n | JavaScript sem teste dentro de JSON de workflow, o mesmo argumento da D17 e do ADR 0001 |
| Guardar a legenda já escapada | O e-mail de aprovação mostraria barras invertidas, e Felipe aprovaria um texto diferente do que escreveu |
| Sem o estado "em publicação", confiando no `published` | Se o LinkedIn publica e o `published` falha (rede, serviço reiniciando), o post seguiria no `due` e sairia de novo no próximo horário |
| Teste de ponta a ponta na fila de produção, limpando depois | Mexeria nos dados reais. O teste usou um volume à parte (abaixo) |

## Consequências

- **Aprendizado do n8n:** o seletor do nó de leitura de arquivo é um glob. Arquivo ausente **não é erro**, é zero itens, e o fluxo para em silêncio (no ramo real, o post ficaria preso em publicação). Por isso o nó `Conferir imagem` usa "sempre gerar saída" e um IF confere se veio o binário. Achado no teste de ponta a ponta, com `mattpocock-skills:diagnosing-bugs`.
- **Positivas:** os workflows não têm regra de negócio; mudar texto de e-mail, regra de escape ou de sombra é mudança testada no Python. Virar o modo sombra é editar uma linha e recriar só o `linky-agents`. Teste de ponta a ponta em 07/11/2026: fila semeada num volume descartável (`linky_teste`) servido por um container de teste com o mesmo alias de rede, com o de produção parado e o volume dele intocado; os três workflows executados pelo CLI; e-mails `[sombra]` entregues na caixa de entrada do Gmail e o alerta confirmado. Rodada final, depois da revisão de código: relógio `01a1b7c6-93eb-712e-a213-2acd6cb065a8`, alertas `01a1b7c6-c957-74bc-97ff-a28b9309c238`, publicação `01a1b7c9-43f1-73dd-b3ee-766c1d826791` e publicação com imagem ausente `01a1b7c8-f45d-7346-8407-dacf7d53a788` (IDs do Resend).
- **Negativas:** o ramo real da publicação (marcar em publicação, LinkedIn, `published`/`failed`) **não foi executado** nesta etapa, por regra; ele reproduz o fluxo do T3, mas o formato do item de erro do n8n e o URN no cabeçalho só serão vistos na primeira publicação real. Recomendação: a primeira publicação fora da sombra deve ser acompanhada. Em sombra, um post aprovado e vencido no horário gera o e-mail "Publicaria agora" a cada horário de publicação, porque a fila não muda. Eventos do `tick` continuam na resposta (ADR 0003): se o Resend falhar depois do `tick`, o e-mail se perde, mas a mudança na fila não. Falha de publicação ainda não avisa por e-mail (etapa E); se o próprio `published` ou `failed` não chegar ao serviço, o post fica em publicação e só é visto na fila. **Post atrasado passa à frente:** o `due` não tem limite para trás e o workflow leva o de horário mais antigo, então um post aprovado cujo horário passou (por exemplo, durante a sombra) sai no próximo horário real, e o post daquele dia espera a execução seguinte. A mitigação, por enquanto, é conferir a fila antes de sair da sombra (`ops/README.md`); uma regra para posts que perderam o horário fica para a etapa E. O remetente e o destinatário estão fixos nos três workflows: mudar exige reimportar os três.

## Atualização (etapa E, 09/11/2026)

- **Falha de publicação agora avisa:** `POST /entries/{id}/failed` grava um alerta `publish_failed` na caixa de alertas, entregue pelo `linkyLedgerAlerts` (sem mudar o workflow). Erro com `401` sugere conferir o token.
- **Post preso em publicação agora avisa:** o `POST /tick` procura posts em publicação há 30 minutos ou mais sem `published`/`failed` e grava um alerta `publishing_stuck` (uma vez por marcação).
- **Token do LinkedIn:** a validade é registrada no serviço (`POST /linkedin/token`, o n8n não expõe essa data); o `tick` grava `linkedin_token` a 7 dias, na véspera e depois de vencer, e uma vez se a data não estiver registrada.
- O `linkyLedgerAlerts` passa a entregar alertas de custo e de operação. Os alertas usam a caixa (durável, deduplicada) e não o e-mail do `tick`, que se perde se o envio falhar.
- **Continua pendente:** a regra para posts aprovados que perderam o horário ("post atrasado passa à frente", acima). Não entrou na etapa E.

## Atualização (etapa H, 10/11/2026): regra do horário perdido

Resolve o "post atrasado passa à frente" (Consequências). Decidida por Claude dentro do PRD §7.6: nunca publicar sem aprovação, data escolhida por Felipe nunca é movida, revalidação de 48 h e validade da pauta. **Nenhum workflow mudou.**

- **`GET /due` só devolve o post do dia:** aprovado, com horário já chegado e no mesmo dia (fuso de Brasília). Uma execução atrasada do `linkyPublish` no mesmo dia (n8n voltou às 22:00) ainda publica; um post de um dia anterior nunca sai no horário de outro, mesmo se o relógio estiver parado.
- **O `tick` trata o horário perdido** (post aprovado cujo dia passou; na prática, na primeira passagem depois da meia-noite):
  - **flexível** ("próximo horário livre"): vai para o próximo horário livre dentro da validade, **continua aprovado** e gera o evento `missed_rescheduled` ("Post remarcado"). Como foi aprovado há mais de 48 h do novo horário, a revalidação de sempre sai no dia (a mesma regra da antecipação, que também move post flexível sem nova aprovação);
  - **data escolhida por Felipe**: não sai sem ele. Volta para **aguardando aprovação**, com o próximo horário livre como sugestão, e gera `missed_reapproval` ("Post perdeu a data escolhida"). A versão da pauta sobe, então o `linkyApprovalEmails` manda um novo e-mail de aprovação; dali em diante valem as regras de sempre (lembrete, adiamento, vencimento);
  - **sem horário livre antes de vencer**: vence (`expired`, com "perdeu o horário de ... e não há horário livre antes de vencer"). É a regra de validade do PRD §7.6; Felipe é avisado, mas não há o que decidir sobre uma pauta vencida.
  - **Ordem e prazo:** o horário perdido é tratado no começo do `tick`, antes do adiamento de quem não foi aprovado: post já aprovado tem preferência nos horários livres, e entre eles escolhe primeiro o que vence antes. O flexível pode pegar o horário de hoje mesmo depois do prazo de aprovação (16:30), porque já está aprovado; o de data escolhida, que volta para aprovação, só pega horário com prazo ainda aberto.
  - Ao voltar para aprovação, o post **continua com data escolhida**, agora no horário sugerido: foi Felipe que fixou a data, e aprovar o horário sugerido é aceitar uma nova data fixa (não é antecipado). Só vira flexível se ele trocar para "próximo horário livre". Sem aprovação no prazo, o adiamento de sempre o torna flexível, como a qualquer post não aprovado. O e-mail de aprovação novo sai porque o `approval_outbox` só considera formulários criados depois que a pauta voltou a aguardar aprovação.
- Nunca toma o horário de outro post: só usa horários livres. Post em publicação, publicado ou com falha não é tocado (o preso em publicação continua com o alerta da etapa E).
- Os e-mails saem pelo e-mail do `tick`, redigidos no serviço, como os outros eventos da fila.

**Alternativas:** publicar o post que perdeu o horário no próximo horário livre sem distinguir data fixa (fere "data escolhida nunca é movida"); estado novo "horário perdido" à espera de Felipe (mais um estado nos formulários; voltar para aguardando aprovação reaproveita o e-mail, o formulário e os prazos que já existem); alerta na caixa de alertas em vez de evento (é uma mudança na fila, como adiamento e vencimento, e não uma falha de operação; a falha, se houver, já tem alerta próprio).

**Consequência em sombra:** como nada é publicado, todo post aprovado perde o horário e é remarcado (ou volta para aprovação) na noite seguinte, com o e-mail `[sombra]`. Substitui o "Publicaria agora" repetido a cada horário descrito acima. Na sombra do T2 a fila real está vazia, então nada muda hoje.
