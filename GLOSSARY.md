# Glossário do linky-dev

Termos do domínio, com o sentido usado no código e nos documentos.

## Harness de agentes

**Agente**: uma etapa da esteira que precisa decidir algo e por isso chama um modelo (triagem, curadoria, redação, checagem, arte). Coleta, renderização e publicação são código determinístico, não agentes.
_Evite_: bot, assistente.

**Contrato**: os tipos de entrada e de saída de um agente. A saída do modelo só é aceita se respeitar o contrato.

**Execução**: uma chamada lógica a um agente, do pedido até a saída validada (ou a falha). Pode envolver várias tentativas e mais de um modelo, e sempre gera um registro.
_Evite_: job, request.

**Tentativa**: uma chamada à API de um modelo dentro de uma execução. Toda tentativa paga entra no ledger.

**Nova tentativa**: repetir no mesmo modelo. Por saída inválida (uma vez, com o erro como contexto) ou por erro transitório do fornecedor (até duas vezes, com espera crescente).
_Evite_: retry, para não confundir os dois motivos.

**Cadeia de fallback**: a ordem dos modelos de um agente, do inicial para os reservas.

**Troca**: a passagem de um modelo para o próximo da cadeia, sempre registrada com o motivo.

**Modelo reserva**: qualquer modelo depois do primeiro na cadeia.

**Fornecedor**: a empresa que serve o modelo pela API (OpenAI, DeepSeek, Anthropic).
_Evite_: provedor, para não confundir com o provedor de e-mail.

**Ledger**: o livro de custos. Uma linha por tentativa paga, com o uso real devolvido pela API e o custo pela tabela de preços vigente.

**Teto**: limite de gasto em dólares por execução, por dia ou por mês. Uma chamada cujo pior caso estoure um teto não acontece.

**Pior caso**: custo máximo possível de uma chamada antes de ela acontecer: entrada estimada mais a saída máxima do agente.

**Documento não confiável**: texto vindo da web. Entra no prompt delimitado, como dado, nunca como instrução.

**Alerta**: aviso durável na caixa de alertas (`alerts.db`) do serviço. De custo: o gasto cruzou 80% do teto do dia ou do mês, ou uma chamada foi bloqueada por um teto. De operação (etapa E): publicação com falha, publicação sem confirmação (post preso em publicação) e validade do token do LinkedIn (a 7 dias, na véspera, vencido ou não registrada). O serviço só registra, cada aviso de operação uma vez; quem entrega (por e-mail) é o n8n. O alerta fica pendente até a confirmação.
_Evite_: notificação, evento (evento é da fila).

**Confirmação**: o n8n avisar que já entregou um alerta. Ler os alertas não os consome; sem confirmação, eles continuam pendentes e são lidos de novo.
_Evite_: ack, em texto.

## Coleta e triagem

**Item**: uma notícia como o coletor gravou: um link de uma fonte, com título, resumo e data de publicação.
_Evite_: notícia, artigo (uma notícia pode ter vários itens).

**Fato**: o acontecimento que um ou mais itens noticiam, em qualquer fonte e idioma. Um fato tem um item representante e as fontes irmãs; é o fato, e não o item, que a triagem avalia e que vira pauta. Um caso que se desdobra por dias (o do CEO da Nvidia) pode ser um fato só.
_Evite_: evento (evento é da fila), cluster, grupo.

**Representante**: o item que fala pelo fato na triagem e no card: o mais parecido com os demais itens do fato.

**Fontes irmãs**: os outros itens do mesmo fato. Entram como fontes do card.

## Fila editorial

Os termos da fila (pauta, horário, reserva, validade, banco, modo silencioso) estão definidos no [ADR 0001](docs/adr/0001-fila-editorial.md) e no PRD §7.6.

**Lote**: as pautas enviadas num mesmo e-mail de pautas. Na esteira, o ID do lote é o horário agendado do envio (`AAAA-MM-DD-HHMM`), e não o relógio: a curadoria que o n8n chama segundos depois das 07:00 cai no lote das 07:00. Responder a qualquer pauta do lote, ou dizer "nenhuma hoje", conta como resposta ao lote. Um lote só entra na fila uma vez.
_Evite_: batch, em texto.

**Evento da fila**: o que o relógio da fila devolve para o n8n comunicar: pauta vencida, post adiado, lembrete de aprovação, post antecipado, revalidação ou horário perdido. Diferente do alerta: o evento vai no e-mail do próprio relógio e não espera confirmação; o alerta fica na caixa até o n8n confirmar.

**Relógio**: a passagem de hora em hora em que a fila vence pautas, adia posts sem aprovação, lembra e antecipa.
_Evite_: cron, job.

**Pedido** (ADR 0008, a construir): um post que Felipe pede por e-mail (`pedido@in.example.com`), fora das pautas da curadoria. Entra na fila já escolhido, com a origem `pedido`, e segue a redação e a aprovação normais. Tem três tipos: **notícia** (com link ou só descrita; a notícia de verdade precisa ser achada), **tema livre** e **experiência** (só o que Felipe escreveu é fato).
_Evite_: solicitação, ordem, ticket.

**Remarcação**: tirar um post do horário dele porque um pedido de Felipe pediu aquela data. O post vai para o próximo horário livre depois dela, continua aprovado e Felipe é avisado; se passar da validade, volta para ele decidir. É a única situação em que um post com data escolhida se move.

**Urgente**: um pedido que Felipe diz que "tem que sair hoje". Sai às 18:30 em qualquer dia da semana (aprovação até 18:15; depois disso, ~15 min após aprovar; sem aprovação até 22:00, volta à regra normal). Nunca pula a aprovação.

**Post**: o que vai ao LinkedIn para uma pauta: legenda, texto alternativo e imagem. Entra na fila quando fica pronto e é o que Felipe aprova, exatamente como escrito. Sem post, não há aprovação.
_Evite_: rascunho, publicação (publicação é o ato de enviar).

**Em publicação**: o post saiu da fila de publicação e está sendo enviado ao LinkedIn. Fica assim até o resultado (publicado ou falhou) e nunca é reenviado sozinho.
_Evite_: reserva, reservado (reserva é do horário, quando a pauta é escolhida).

**Horário perdido**: o dia de publicação de um post aprovado passou sem que ele saísse (o n8n estava fora do ar ou o sistema estava em modo sombra). O post nunca ocupa o horário de outro dia: com "próximo horário livre", vai para o próximo horário livre antes de vencer e continua aprovado; com data escolhida por Felipe, volta para a aprovação; sem horário antes de vencer, vence.
_Evite_: atrasado, pendente (não diz se ainda pode sair).

**Modo sombra**: o sistema roda inteiro, mas não publica nada: no horário de publicação, só avisa por e-mail o que sairia. Todo e-mail em sombra tem o assunto começando por "[sombra]". Usado enquanto o T2 publica à mão.
_Evite_: modo de teste, dry-run.

## Decisões por e-mail (etapa D, ADR 0005)

**Decisão 1**: a escolha das pautas, no e-mail de pautas. Por pauta: produzir para o próximo horário livre, produzir para uma data, guardar no banco ou descartar, com a opinião opcional em uma linha. "Nenhuma hoje" também é resposta.

**Decisão 2**: a aprovação do post. Aprovar (podendo trocar o horário), pedir ajuste, descartar ou só trocar o horário.

**Formulário**: a página que o link do e-mail abre. Abrir não muda nada; só o **envio** (o botão) decide. O formulário mostra a pauta como ela está agora, então um e-mail antigo continua valendo enquanto a pauta valer.
_Evite_: link de ação, botão no e-mail.

**Token de uso único**: o campo oculto de cada pauta no formulário. Vale para uma decisão sobre a pauta na versão em que a página foi aberta; usado uma vez, não vale de novo.
_Evite_: senha, chave.

**Versão da pauta**: número que sobe a cada mudança que Felipe decide ou vê (escolha, horário, post novo, ajuste). Lembrete e revalidação não sobem a versão.

**Ajuste**: pedido de Felipe para refazer o post, com o que mudar. Até 3 por pauta; a pauta volta a escolhida, com o horário mantido, até a nova versão do post chegar.
_Evite_: revisão, correção.

**Pauta liberada**: pauta escolhida cuja redação falhou 2 vezes. Ela volta ao banco, libera o horário e reaparece na repescagem (`Queue.release`).

**Repescagem**: até 3 pautas de e-mails anteriores, ainda válidas e não escolhidas (sem resposta ou no banco), repetidas no e-mail de pautas seguinte (as que vencem primeiro).

## Imagem (ADR 0002 e ADR 0006)

**Composição**: a descrição de uma imagem de post: o tema, o fundo e as peças. É o que o agente de direção de arte entrega e o que o motor valida antes de desenhar.
_Evite_: layout, molde, template (os 3 layouts antigos são só exemplos).

**Tema**: claro (papel) ou escuro (grafite). Define o fundo e a cor de cada papel do texto (texto, apoio, fio, superfície, retícula); Felipe alterna claro e escuro entre posts.
_Evite_: modo noturno, dark mode.

**Peça**: uma parte da composição com sentido próprio (manchete com destaque, pilhas antes e hoje, linha do tempo, rodapé com fio). Pode vir de um componente ou ser livre, feita de primitivos.
_Evite_: bloco (bloco é o de destaque), widget.

**Componente**: uma peça da biblioteca (`render.components`), extraída das imagens do T2: uma função que recebe o conteúdo e alguns ajustes e devolve a peça pronta, com o ID do componente como nome (empresa e contexto, manchete com destaque, rodapé com fio, retícula ancorada, barras sangrando, diagrama de passagem). Não é molde: o agente escolhe quais usar e onde, e o resto da imagem continua livre.
_Evite_: template, layout, widget.

**Número com legenda**: o átomo das listas, grades e trios de números (marcador violeta, número grande, uma ou duas linhas de legenda). É uma parte, não uma peça: entra numa peça livre.

**Bloco de destaque**: o retângulo violeta ou lilás atrás de uma palavra da manchete. Cobre toda a tinta da palavra, inclusive acento e cedilha.

**Retícula**: textura de pontos de uma cor da paleta, sempre nascendo de uma borda ou de uma estrutura (a âncora) e diminuindo para longe dela. Nunca solta no meio do espaço e nunca embaixo de texto.
_Evite_: halftone, em texto.

**Faixa do rodapé**: a área abaixo do fio do rodapé, onde ficam a fonte e a assinatura. É a única parte em que texto pode entrar na margem de 72 px.

**Recusa**: o motor não desenha uma composição que quebra uma regra da marca e devolve todos os motivos, cada um com a peça e o elemento, para o agente corrigir.
_Evite_: erro de layout (é o texto que não cabe), falha.

**Achado conhecido**: uma violação já vista e aceita por uma pessoa numa imagem específica (hoje, as imagens já publicadas do T2). Nunca vem do agente.

**Assinatura da composição**: o tema e o fundo mais o conjunto das peças, sem texto e sem posição. Duas imagens com a mesma assinatura são a mesma composição.
_Evite_: assinatura, sozinha (a assinatura do post é "Felipe Lenzi · IA aplicada a negócios").

**Repetição**: usar uma composição cuja assinatura já apareceu nos últimos 5 posts. É motivo de recusa.

## Repositório e segurança

**Retrato público**: o repositório `LenziAI-DEV/linky`, gerado do `linky-dev` privado pelo `tools/public/export_public.py`, sem histórico e com os identificadores reais trocados (ADR 0010). Não é um espelho: só muda quando alguém publica um novo retrato.
_Evite_: fork, mirror.

**Padrão proibido**: um texto (e-mail, domínio, IP, host, ID de credencial, nome de terceiro) que não pode aparecer no retrato público. Se sobrar um, a exportação falha.

**Fonte recusada**: um link de notícia, ou um redirecionamento dele, que o `netguard` não deixa baixar porque pode alcançar a rede interna (SSRF). A fonte fica de fora e o post segue com as outras.
