# ADR 0005: e-mails das duas decisões com formulário servido pelo n8n e token de uso único

- **Status:** aceita · **Data:** 09/11/2026 · **Decisores:** Claude (arquitetura), dentro das regras de Felipe (duas decisões por e-mail, sempre por formulário com botão de envio, nunca por link de clique único)

## Contexto

A etapa D liga as duas decisões de Felipe (PRD §7.1) à fila editorial (ADR 0001) já exposta pelo serviço `linky-agents` (ADR 0003) e pelos workflows da etapa C (ADR 0004):

- **Decisão 1 (pautas):** seleção múltipla; por pauta, produzir para o próximo horário livre, para uma data ou guardar no banco, com opinião opcional em uma linha; "nenhuma hoje"; agenda e repescagem no e-mail.
- **Decisão 2 (aprovação):** aprovar (podendo trocar o horário), pedir ajuste (até 3 rodadas), descartar ou só trocar o horário.
- **Scanners de link** (pré-busca do Gmail, antivírus corporativos, pré-visualização de mensageiros) abrem links sozinhos. Um link que decide algo por GET pode aprovar ou descartar sem Felipe (T4′, PRD §7.5).
- O serviço não tem rota pública (ADR 0003): só o n8n o alcança. O n8n de produção é compartilhado com outro projeto e não pode ser reiniciado; workflows com gatilho só ligam pela interface.
- Clientes de e-mail tratam `<form>` dentro do e-mail de forma desigual (avisos, envio bloqueado ou formulário removido, conforme o cliente), então o formulário não pode depender do corpo do e-mail.

## Decisão

1. **O e-mail leva só um link; o link abre uma página; só o envio da página decide.** A página do formulário é servida por um webhook do n8n (`GET /webhook/linky-form?f=<id>`); o envio vai para o mesmo endereço por `POST`. O GET **nunca muda nada** (nem "visto", nem contador): é seguro para qualquer scanner.
2. **Páginas e e-mails redigidos no serviço, como no ADR 0004.** O workflow `linkyForms` só repassa: `GET /forms/{id}` devolve `{status, html}`; `POST /forms/{id}` recebe `{fields}` (o corpo do formulário como o webhook o entrega) e devolve a página de resultado. O status HTTP da página vem no corpo, para o n8n repassá-lo sem tratar erro.
3. **Token de uso único por pauta.** Cada pauta do formulário leva um campo oculto `t:<pauta>` = HMAC-SHA256(chave, formulário | pauta | versão), com a chave derivada do segredo do serviço (`LINKY_SERVICE_TOKEN`). Nada fica guardado além do registro de uso: o token vale uma vez (tabela `used`) e toda decisão sobe a `version` da pauta, então reenviar a mesma página (voltar, duplo clique, robô) é recusado sem mudar nada. Reabrir o link gera a página com o token da versão atual. Lembrete e revalidação do relógio não sobem a versão, para não invalidar uma página aberta. "Nenhuma hoje" tem o próprio token, um por formulário.
4. **O padrão é não decidir.** Cada pauta começa em "Não decidir agora" e o "nenhuma hoje" começa desmarcado. Um envio do formulário como veio volta "Nada foi marcado. Nada mudou." (400). Cada pauta é decidida por si: um erro numa (data sem horário, pauta vencida) não impede as outras. A página de resultado vem com 200 se alguma decisão valeu, senão 409 (token velho ou regra da fila, como no ADR 0003).
5. **Formulários guardados em `forms.db`** (`forms`: id aleatório de 128 bits, tipo, pautas, versão do post, envio; `used`: escopo, formulário, ação). O id é o que dá acesso à página; quem tem o e-mail tem o formulário, como em qualquer link de e-mail.
6. **Formulário vivo, não instantâneo.** A página mostra o estado atual da pauta: pauta já respondida aparece como respondida, vencida como "venceu", versão de post substituída por um ajuste como "a nova versão está em outro e-mail". As datas oferecidas são os horários livres (ou o da própria pauta) dentro da validade e com prazo de aprovação no futuro (`Queue.free_slots`).
7. **O que cada formulário oferece.** Decisão 1: as três opções do PRD (próximo horário livre, data, banco) e também **descartar**, para tirar da repescagem uma pauta que não interessa. Decisão 2: aprovar (com troca de horário), só trocar o horário, pedir ajuste (enquanto houver rodada) e descartar; depois de aprovado, o mesmo formulário ainda permite trocar o horário ou descartar, que é o caminho que o aviso de revalidação já indica ("para segurar, descarte ou remarque antes das 18:30"). O limite "de 0 a 3 pautas" não é contado no formulário: cada escolha reserva um horário diferente, e o e-mail traz no máximo os cards do horário (3, ou 5 no domingo) mais 3 da repescagem.
8. **Fila:** a pauta ganha `what`, `why`, `angle` (o card), `opinion`, `adjustments` e `version`; nova transição `request_changes` (aguardando aprovação → escolhida, horário mantido, até 3); `choose` e `bank` aceitam a opinião; `proposal_plan` passa a separar `new` (pautas registradas desde o envio anterior, até o número de cards do horário, as de maior nota; as que sobram vão à repescagem) de `carry_over` (repescagem, até 3, das que vencem primeiro). **Correção do modo silencioso:** qualquer resposta passa a marcar também o lote mais recente, para que responder a uma pauta da repescagem tire do silêncio ("qualquer resposta reativa tudo", PRD §7.6); antes, só o lote antigo da pauta era marcado.
9. **Três workflows novos**, gerados por `tools/n8n_etapa_d.py`, importados inativos:

   | ID | Gatilho | Fluxo |
   |---|---|---|
   | `linkyProposals` | `0 7 * * 1-5` e `0 21 * * 0` | `POST /proposal_email` → e-mail (se houver). Quando a curadoria existir, ela entra antes (`POST /propose`) |
   | `linkyApprovalEmails` | `*/15 * * * *` | `POST /approval_emails` → 1 post por execução → lê a imagem → Resend com a imagem anexada e embutida (`cid:linky-post`) e `Idempotency-Key` por formulário → `POST /forms/{id}/sent`. Sem confirmação, o e-mail volta na execução seguinte, e a chave faz o Resend não mandar de novo o que já mandou (24 h). Imagem ausente: e-mail com "IMAGEM NÃO ENCONTRADA" no assunto |
   | `linkyForms` | webhook `linky-form`, GET e POST | repassa ao serviço e responde a página com `Cache-Control: no-store`, `X-Robots-Tag: noindex` e `Referrer-Policy: no-referrer`. O `f` é validado (`[A-Za-z0-9_-]{8,64}`) e codificado antes de entrar no caminho, para nunca alcançar outra rota |

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Botões que decidem por GET (`?acao=aprovar&t=...`) | É o "link de clique único" proibido no PRD: um scanner aprova ou descarta sozinho |
| `<form method=post>` dentro do e-mail | Suporte desigual entre clientes (aviso, envio bloqueado ou formulário removido); não verificado aqui, e o link para a página funciona em todos |
| Form Trigger / nó Form do n8n | Campos definidos no workflow, sem teste e difíceis de gerar por pauta; a regra (o que cada pauta pode fazer agora, datas livres) ficaria em JavaScript dentro do JSON, o mesmo argumento da D17 e do ADR 0004 |
| Token aleatório guardado por pauta | Guardar segredo em claro no banco, ou só o hash e não conseguir remontar a página. O HMAC de (formulário, pauta, versão) não precisa ser guardado |
| Token sem versão, só a tabela de uso | Uma pauta no banco não poderia ser escolhida depois pelo mesmo formulário, e "só trocar o horário" travaria a aprovação |
| Página que pede confirmação extra (dois passos) | Mais atrito para Felipe sem proteção a mais: o envio já exige escolha explícita e token |

## Consequências

- **Positivas:** nenhum GET decide nada, e isso é testado (`test_abrir_o_formulario_nao_muda_nada`: os bancos ficam byte a byte iguais). Regras e páginas ficam no Python, com 20 testes na interface que o n8n usa. Formulário antigo continua valendo enquanto a pauta valer, como pede o PRD §7.6.
- **Negativas:** rodar o e-mail de pautas duas vezes cria dois formulários para as mesmas pautas; os dois valem, e a primeira decisão invalida o token do outro (versão). O modo silencioso de domingo só leva um aviso no e-mail, não um resumo à parte. Trocar o `LINKY_SERVICE_TOKEN` invalida os tokens das páginas abertas (basta reabrir o link). Quem tiver o e-mail tem o formulário (o mesmo vale para qualquer link de e-mail; o webhook é público). Uma pauta respondida por outro formulário enquanto a página está aberta mostra "nada foi alterado, abra o link de novo". A imagem do post vai anexada; se o Resend deixar de aceitar `content_id`, ela continua anexada, só não aparece no corpo. Em sombra, as decisões mudam a fila de verdade (só a publicação é simulada): o volume de produção segue vazio até o fim do T2, e os testes usam um volume descartável.
- **T4′ (09/11):** passou. T4′ ao vivo (09/11, ~22:45 a 22:53): `tools/t4_scanners.py` contra o webhook público, nos formulários de pautas e de aprovação. GET e HEAD com os user-agents do proxy do Gmail, Google Safe Browsing, Outlook Safe Links, Proofpoint, Slack, WhatsApp, Facebook e Bing (GET 200; HEAD 404, o n8n não registra HEAD), o rastreador seguindo os links da página e o robô que envia o formulário como veio (400, "Nada foi marcado"): SHA-256 de `editorial.db` e `forms.db` **idênticos** antes e depois, nos dois formulários. O envio de verdade valeu (200) e o reenvio igual foi recusado (409). Nas 60 execuções do `linkyForms` desde a ativação, nenhum acesso de terceiros (só os testes e uma conferência da sessão principal), com três e-mails `[sombra]` com links na caixa de entrada do Gmail durante a janela. Limite: o Gmail não é um scanner agressivo; antivírus corporativos (Safe Links de verdade, Proofpoint) foram simulados pelo user-agent, não por uma conta real.
- **Ativação:** `linkyForms` precisa estar ativo para os links funcionarem (ativação pela interface, por Felipe). `linkyProposals` e `linkyApprovalEmails` podem ficar ativos em sombra: com a fila real vazia, não mandam nada.
