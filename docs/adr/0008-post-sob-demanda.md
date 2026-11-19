# ADR 0008: post sob demanda por e-mail

- **Status:** aceita (desenho; construção depois da calibração do T2) · **Data:** 11/11/2026 · **Decisores:** Felipe (produto, nas 25 perguntas do grilling da sessão 6) e Claude (arquitetura)

## Contexto

A esteira só cria posts a partir das pautas que a curadoria propõe. Felipe quer também **pedir um post específico**: uma notícia que viu, um tema, ou uma experiência dele. Restrições:

- **Sem interface própria.** O pedido tem de caber no modelo atual: e-mail, formulários servidos pelo n8n (ADR 0005), serviço `linky-agents` (ADR 0003).
- **Mesma infraestrutura de agentes.** O pedido usa o mesmo redator, o mesmo gerador de imagem e o mesmo teto de custo (US$ 3/mês) da esteira. Nenhum agente próprio.
- **Mesmas garantias.** Nada sai sem aprovação explícita do texto e da imagem exatos. No máximo 1 post por dia, salvo exceção dita por Felipe.

Dois fatos levantados na sessão 6 pesaram:

- **O harness não tem nenhum agente registrado.** `prompts/` está vazio. O redator e o gerador de imagem são o próximo passo do MVP e dependem da calibração do T2. O pedido é, portanto, **construído junto com o redator**, não antes. Antes disso, só daria para fazer um redator provisório que iria para o lixo.
- **O domínio `example.com` não recebe e-mail.** Não tem MX. O Resend, que já envia, também recebe (Resend Inbound, plano Free), num subdomínio próprio e sem tocar no domínio principal. O webhook `email.received` traz só os metadados. A API "Retrieve received email" devolve o corpo, os anexos e o veredito de SPF/DKIM/DMARC calculado pelo próprio Resend.

## Decisão

### Entrada

1. **Canal:** e-mail para **`pedido@in.example.com`**, recebido pelo **Resend Inbound** no subdomínio `in.example.com` (um MX no Cloudflare, criado por Felipe pela interface).
2. **Quem pode pedir:** só `voce@example.com`, com **`dkim=pass` e `dmarc=pass`** no veredito do Resend, e com a assinatura do webhook conferida. Qualquer outro remetente é **ignorado em silêncio**: sem resposta, para não confirmar a terceiros que o endereço existe. Um endereço novo de Felipe entra por configuração.
3. **Um pedido por assunto.** Um e-mail com dois assuntos vira dois pedidos, e a confirmação lista os dois.
4. **Classificação automática:** Felipe não marca nada. Um agente barato, o **intérprete do pedido**, lê o e-mail e devolve:
   - o tipo;
   - o ângulo;
   - a data pedida, se houver;
   - se é **urgente** ("tem que sair hoje");
   - se pede para **somar** a um post do dia ("além do de hoje");
   - o assunto de cada pedido.

### Tipos de pedido e de onde vêm os fatos

| Tipo | Exemplo | Fatos | Sem material suficiente | Validade |
|---|---|---|---|---|
| **Notícia** (com link ou só descrita: o caso comum) | "crie um post sobre a notícia da empresa X que fez isso, isso e isso" | Precisa achar a notícia de verdade: primeiro a base coletada (fatos da etapa H), depois **até 3 buscas na web**. Se a fonte disser algo diferente da descrição, **vale a fonte**, e a divergência aparece na confirmação | Não escreve. Responde dizendo o que procurou | Perecível |
| **Tema livre** | "escreve sobre agentes no varejo" | Mesmo caminho: base coletada, depois até 3 buscas. **Todo fato do post precisa de uma fonte lida** | Não escreve. Responde com o que achou | Durável |
| **Experiência** | "implantei X na empresa e aprendi Y" | **Só o que Felipe escreveu.** O redator organiza e ajusta à voz, mas não acrescenta número, empresa, estudo nem detalhe. Dado externo só se vier um link junto | **Pergunta o que falta** (situação, o que fez, resultado, lição), sem inventar | Durável |

O post de experiência usa o **formato de relato** do `voz.md` (§6.1), não a estrutura canônica de notícia.

### Imagem

5. **Sem anexo:** a imagem sai do motor de composição, igual à da esteira (ADR 0002 e 0006, biblioteca de componentes).
6. **Com anexo:** a geração de imagem é **pulada**. O post usa as imagens de Felipe **como vieram**, sem moldura, logo ou texto da marca, **na ordem dos anexos, até 9**. Um modelo com visão escreve o texto alternativo de cada uma, e Felipe confere no e-mail de aprovação. Imagem fora do formato aceito pelo LinkedIn (tipo ou tamanho) é recusada na confirmação, com o motivo.
7. A alternância de tema claro e escuro e o registro contra repetição valem só para as imagens do motor. Imagem de Felipe não entra no registro.

### Fila e calendário

8. **O pedido entra na fila como um post normal**, já escolhido. Ele pula a decisão 1 e segue a fila editorial (ADR 0001): redação, e-mail de aprovação com formulário (decisão 2: aprovar, ajustar, descartar, trocar o horário), publicação. A entrada ganha a origem `pedido`, para separar das pautas da curadoria no gold set e nas métricas.
9. **Horário padrão:** o próximo horário livre (seg, qua ou sex, 18:30).
10. **Data pedida:** o pedido fica com a data. Se ela já tiver um post, esse post é **remarcado para o próximo horário livre depois dela**, nunca antes:
    - a remarcação vai em cascata, um post por vez: se o próximo horário estiver ocupado, vai para o seguinte livre, sem empurrar ninguém;
    - o post remarcado **continua aprovado**, porque o texto e a imagem não mudaram, só a data, e Felipe recebe um aviso;
    - se ele for perecível e a nova data passar da validade, **volta para Felipe decidir** (banco ou descarte) em vez de vencer em silêncio.
11. **Pedido depois do prazo de aprovação do dia** (16:30): vai para o próximo horário livre, e a confirmação explica por quê.
12. **Urgente** ("tem que sair hoje"):

    | Situação | O que acontece |
    |---|---|
    | Horário | 18:30 do dia, **em qualquer dia da semana** |
    | Prazo de aprovação | 18:15 |
    | Aprovado depois de 18:15 | Publica ~15 min depois da aprovação |
    | Sem aprovação até 22:00 | Não sai no dia: volta à regra normal (item 9), com aviso |
    | Dia que já tem post | O outro post é remarcado pelo item 10. Só fica com 2 posts se Felipe disser "além do de hoje" |

    A urgência **nunca pula a aprovação**.

### Conversa por e-mail

13. **Confirmação em ~1 minuto**, na mesma conversa (`In-Reply-To` e `References`), com:
    - o tipo entendido, o ângulo e o horário reservado;
    - a divergência com a fonte e os anexos recusados, se houver;
    - o aviso de remarcação, se tirou algum post do lugar.
14. **Resposta na conversa = ajuste** daquele pedido. Texto ou imagem nova geram uma **nova versão**, que volta para aprovação. A aprovação em si continua só no formulário (ADR 0005), pelo e-mail de aprovação.
15. O e-mail de aprovação do pedido é o mesmo da decisão 2 (`POST /approval_emails`).

### Lançamento

16. **Construção junto com o redator do MVP**, depois da calibração de 13/11.
17. **Primeiro em modo sombra**, como as etapas C a E. Os pedidos reais geram confirmação e aprovação com `[sombra]`, mas nada é publicado e nenhum post da fila real é remarcado. O pedido sai da sombra junto com o resto do MVP.

## Arquitetura (o que muda)

| Peça | Mudança |
|---|---|
| Resend | Recebimento ativado no subdomínio `in.example.com` e webhook `email.received` apontando para um webhook novo do n8n. **Ação de Felipe:** registro MX no Cloudflare e ativação na conta do Resend |
| n8n | Workflow novo `linkyRequests`. Recebe o webhook, confere a assinatura e busca o e-mail completo pela API (credencial `Resend linky`; conferir se a chave só de envio lê e-mails recebidos, senão criar uma chave de leitura restrita). Repassa ao serviço e envia a confirmação. Não decide nada |
| Serviço `linky-agents` | Rota nova `POST /requests`, que faz:<ul><li>confere remetente e veredito;</li><li>chama o intérprete;</li><li>cria as entradas com origem `pedido`;</li><li>aplica a remarcação;</li><li>redige a confirmação;</li><li>idempotente pelo `Message-ID` do e-mail.</li></ul>Os anexos são guardados no volume `/data`. Uma resposta na conversa é ligada ao pedido pelo `In-Reply-To` |
| Fila editorial | Origem `pedido`; data pedida que **remarca** quem estava (hoje, data escolhida nunca é movida: a exceção é só para o pedido de Felipe); estado de **urgente**, com prazo de 18:15 e janela até 22:00; post com **várias imagens** |
| Agentes (harness) | Novos:<ul><li>**intérprete do pedido** (modelo barato);</li><li>**pesquisa** (base coletada + busca na web, até 3 buscas, saída com as fontes lidas);</li><li>**texto alternativo** (modelo com visão).</li></ul>O **redator** e o **gerador de imagem** são os mesmos da esteira. O redator recebe o tipo do pedido para escolher a estrutura |
| Relógio | Passa a rodar **a cada 15 minutos**: urgentes aprovados e a janela das 22:00. Os outros eventos continuam de hora em hora, como hoje |
| Publicação | `linkyPublish` aceita várias imagens (API de várias imagens do LinkedIn, teste ao vivo antes de sair da sombra) e um disparo fora de seg, qua e sex 18:30 para os urgentes |
| Gold set | Pedidos registrados como dados de avaliação do redator (o que Felipe pediu, a versão aprovada, as edições) |

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Formulário fixo nos favoritos | Exige abrir uma página e digitar. No celular, compartilhar a notícia por e-mail é mais natural, e anexar foto é trivial |
| Rótulo no Gmail lido pelo n8n (Gmail Trigger ou IMAP) | Dá ao n8n acesso amplo à caixa de Felipe. O filtro por remetente usa o `From`, que pode ser forjado. Funciona por polling |
| Cloudflare Email Routing + Email Worker | Grátis e na hora, mas exige um Worker em JavaScript para ler o MIME e põe o MX na raiz do domínio. Há um relato de veredito de autenticação ausente na entrega para Worker. O Resend dá o veredito num campo estruturado e já é o fornecedor de envio |
| Classificação marcada por Felipe (assunto com `[noticia]`, `[tema]`...) | Mais atrito e propenso a esquecimento. A interpretação volta na confirmação e pode ser corrigida respondendo |
| Pedido fora da fila, com publicação direta | Duplicaria aprovação, alertas, horário perdido e publicação, e enfraqueceria a regra de nunca publicar sem aprovação |
| Construir antes do redator do MVP | Exigiria um redator provisório, descartado logo depois |

## Consequências

- **Positivas:**
  - Felipe pede pelo celular, sem interface nova, com as mesmas garantias (aprovação, 1 por dia, teto de custo).
  - Os pedidos viram dados de avaliação do redator com intenção explícita.
  - A experiência pessoal ganha um caminho seguro, que nunca inventa vivência.
- **Negativas e riscos:**
  - **Custo:** a pesquisa na web custa cerca de US$ 0,01 por busca, mais os tokens. O pedido conta no teto de US$ 3/mês e, se o teto bloquear, Felipe recebe um e-mail dizendo que o pedido não foi redigido e por quê.
  - **Remarcação em cascata:** mexe em posts aprovados. Mitigado pelo aviso e pela regra de validade.
  - **Relógio mais frequente:** 4× mais execuções do `tick` no n8n. É leve (o tick só lê a fila), mas acompanhar a memória da VPS.
  - **Várias imagens:** caminho de publicação novo, que não roda em sombra. Precisa de teste ao vivo combinado com Felipe.
  - **Mais uma entrada pública:** é um webhook. Defesas: assinatura do Resend, veredito DKIM/DMARC, lista de remetentes, idempotência pelo `Message-ID` e o próprio teto de custo.
- **Em aberto (decidir na construção):**
  - os modelos do intérprete, da pesquisa e do texto alternativo (pelo T7);
  - os limites de tamanho dos anexos;
  - o texto exato da confirmação.
