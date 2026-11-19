# Rubrica de curadoria (v0, rascunho para a semana Mágico de Oz)

> **Em vigor: v0** (abaixo). Proposta de **v1 em RASCUNHO** no fim deste arquivo ([Rubrica v1](#rubrica-v1-rascunho)), para decidir com Felipe na calibração de 13/11. Nada da v1 vale até a decisão.

Cada item candidato recebe nota de 0 a 3 em cada critério. **Nota final = soma ponderada.** As 3 maiores notas viram os cards do e-mail, desde que passem nos filtros eliminatórios. Os pesos serão recalibrados com as escolhas reais de Felipe na Fase 0.

## Filtros eliminatórios (qualquer “não” descarta o item)

1. O fato aconteceu ou foi anunciado no dia anterior (fuso de Brasília)?
2. Existe uma fonte verificável? Para números ou afirmações fortes: fonte primária, ou duas fontes independentes.
3. Não é publieditorial, rumor sem fonte nem lista genérica (“10 ferramentas de IA…”).

## Critérios

| Critério | Peso | 0 | 3 |
|---|---|---|---|
| **Relevância para negócios** | 3 | Curiosidade técnica sem impacto prático | Muda decisões de empresas: custo, processo, mercado, regulação |
| **Novidade** | 2 | Já amplamente comentado há dias | Fato novo, ou um ângulo que ninguém explorou |
| **Evidência** | 2 | Opinião ou promessa | Caso real, dado, pesquisa ou lançamento verificável |
| **Ângulo Brasil / aplicabilidade local** | 1 | Sem conexão possível | Afeta empresas brasileiras, ou há um paralelo claro |
| **Aderência ao posicionamento de Felipe** | 2 | Fora do território dele | No centro do que ele quer ser referência *(definir em voz.md)* |
| **Potencial de conversa** | 1 | Não gera opinião | Provoca debate, aprendizado ou contraponto |

**Nota máxima:** 33. Desempate: evidência > relevância > novidade.

## Formato de cada card (e-mail da decisão 1)

- **Título** (até 12 palavras)
- **O que aconteceu** (2 frases, só fatos, com fonte)
- **Por que importa** (2 frases, para quem e o quê)
- **Abordagem sugerida** (formato do post + gancho em 1 linha)
- **Fontes** (links) · **Nota** (com o critério mais forte)

## Calibração

- Na semana Mágico de Oz, registrar para cada dia: os 3 cards, a escolha de Felipe e o motivo em uma frase.
- Ao fim da semana, ajustar os pesos para que a pauta escolhida apareça no top 3 em pelo menos 80% dos dias.

---

# Rubrica v1 (RASCUNHO)

> **RASCUNHO de 11/11/2026, não está em vigor.** Proposta para a calibração de sex 13/11, a partir dos 3 dias do gold set (8 escolhas) e dos aprendizados dos dias 1 a 3 (`docs/CONTINUIDADE.md` §4.1). Dados em [`calibracao/02-fim-do-t2-dados.md`](calibracao/02-fim-do-t2-dados.md) e leitura em [`calibracao/02-fim-do-t2-leitura.md`](calibracao/02-fim-do-t2-leitura.md). O código (`linky_agents.gold`) continua na v0 até Felipe decidir.

## Perguntas para Felipe (decidir em 13/11)

1. **Como contar a meta do top 3 nos lotes?** Com 5 escolhas num lote, só 3 cabem no top 3. Opções: (a) por escolha: 6 de 8 = 75% hoje; (b) por dia, com todas as escolhas no top N, sendo N o número de horários do lote (mínimo 3): 2 de 3 dias; (c) por dia, com pelo menos uma escolha no top 3: 3 de 3. *Sugestão:* (a), que é a que mais aprende com amostra pequena.
2. **Diversidade entre os cards: regra dura ou desconto na nota?** *Sugestão:* regra de montagem (abaixo), sem mexer na nota: no máximo 1 card por tema e 1 por empresa principal no mesmo lote.
3. **Diversidade na sequência publicada: qual janela?** *Sugestão:* nunca dois posts seguidos sobre a mesma empresa; no máximo 2 do mesmo tema em 5 posts seguidos. Regra da fila (bloqueia o horário) ou só aviso na sugestão de agenda?
4. **Publieditorial: elimina sempre, ou só marca?** Dois casos diferentes apareceram: conteúdo **patrocinado declarado** (Bain na MIT Technology Review Brasil, passou com nota 26) e **caso de cliente publicado pelo próprio fornecedor** (Greenlight no blog da AWS, card 3 do dia 1; CodeRabbit no blog da OpenAI). *Sugestão:* patrocinado declarado elimina; caso do fornecedor pode virar card, marcado como `[fornecedor]` e com evidência no máximo 1 sem confirmação independente.
5. **O que é "lançamento grande"?** *Sugestão de sinais objetivos:* (a) o fato aparece em 3 ou mais fontes independentes (o agrupamento por fato da etapa H já conta); (b) lidera um índice ou benchmark independente; (c) está disponível para empresas agora, não só anunciado. Com 2 dos 3 sinais, o lançamento não pode ser descartado como "torcida entre modelos".
6. **Análises (HBR, McKinsey) têm lugar?** Elas são relevantes (100% e 50% na triagem), mas o filtro 1 ("aconteceu ontem") as elimina. Abrir exceção para pesquisa ou relatório **novo** publicado na semana, ou deixá-las para o post de tese e fora do card diário?
7. **Mudar pesos agora?** *Sugestão:* não. As duas escolhas fora do top 3 (Fable e Bain) se explicam por regras que faltavam (lançamento grande, publieditorial), não por peso errado, e 8 escolhas não sustentam ajuste fino. Reavaliar os pesos com 4 semanas da Fase 1.
8. **Desempate:** o Fable empatou com o card 3 (27) e perdeu no desempate por evidência. Manter evidência > relevância > novidade?

## O que muda em relação à v0

### Filtros eliminatórios

1. O fato aconteceu ou foi anunciado no dia anterior (fuso de Brasília)? *(igual; ver pergunta 6)*
2. Existe uma fonte verificável? Para números ou afirmações fortes: fonte primária, ou duas fontes independentes. *(igual)*
3. **Não é publieditorial nem conteúdo patrocinado**, rumor sem fonte ou lista genérica. **Novo: como reconhecer**, porque a Bain passou pela v0:
   - selo ou rodapé com "patrocinado", "conteúdo de marca", "publieditorial", "oferecido por", "em parceria com", "branded content", "sponsored", "presented by";
   - a empresa que assina ou patrocina é a mesma que o texto elogia ou cujos dados apresenta;
   - na dúvida, **marcar** (abaixo) em vez de deixar passar calado.

### Marcações (não eliminam, mas aparecem no card)

- **`[patrocinado]`**: só se Felipe decidir que patrocinado não elimina (pergunta 4). Se virar post, o patrocínio é dito na legenda ou na imagem, como no post da Bain.
- **`[fornecedor]`**: caso de cliente publicado pelo fornecedor da tecnologia (blog da AWS, da OpenAI etc.). Evidência no máximo 1, a menos que haja confirmação independente (o cliente, a imprensa).

### Aderência ao posicionamento: lançamento grande com ângulo de capacidade

A v0 punha "guerra de torcidas entre modelos" fora do território, e o Fable 5.2 caiu nesse balaio por engano (dia 2). A v1 separa:

| Fica fora (posicionamento 0 a 1) | Fica dentro (posicionamento 2 a 3) |
|---|---|
| Quem ganhou o benchmark da semana, briga entre empresas ou executivos, especulação sobre o próximo modelo | Lançamento que muda **o que as empresas conseguem fazer**: capacidade nova, custo que muda a conta, disponibilidade corporativa |

- Um lançamento com 2 dos 3 sinais de "grande" (pergunta 5) recebe posicionamento de pelo menos 2.
- **O ângulo acompanha o tamanho do fato.** Lançamento grande e viral pede o **salto de capacidade** (o que passa a ser possível, com exemplos reais); a leitura de custo serve quando o fato é preço. Na abordagem do card, dizer qual dos dois e por quê. (Para o redator, isso vale também em `voz.md`: contenção não é minimizar.)

### Diversidade (regra de montagem, depois da nota)

A nota continua por fato. A diversidade entra na **montagem** dos cards e na **sugestão de agenda**, não na nota, para não esconder um fato forte só porque outro parecido também é forte.

**Entre os cards de um lote:**
1. Ordenar os fatos pela nota (como hoje).
2. Escolher de cima para baixo, pulando o fato cujo **tema** ou **empresa principal** já está num card escolhido.
3. O fato pulado vai para o banco com a nota e o motivo ("mesmo tema do card 1").

Exemplo: no dia 1, Nubank (31) e Greenlight (26) eram ambos "IA em filas de fraude e segurança". Pela v1, o Greenlight cederia a vaga ao fato seguinte.

**Na sequência publicada:**
- Ao sugerir horários, não pôr dois posts seguidos sobre a mesma empresa (o IPO da Anthropic foi movido para o fim da semana para não emendar com Fable e Claude Code) e respeitar a janela de tema da pergunta 3.
- Quando dois posts do mesmo dia conversam (Uber e Adobe sobre agentes, em 12/11), as legendas não podem parecer contraditórias.

### Pesos

**Sem mudança proposta** (pergunta 7): os mesmos da v0, nota máxima 33.

### Meta e como medir

- Meta: a escolha de Felipe no top 3 em pelo menos 80% (definição da pergunta 1).
- Medir com `uv run python -m linky_agents.calibration <itens> --out <relatório>` (seção 1 do relatório).

## Para implementar depois da decisão (não feito)

- `linky_agents.gold`: `RUBRIC_VERSION = "v1"`; no `Card`, campos `topic` e `companies` (para a regra de diversidade); no `ScoredItem`, marcações (`sponsored`, `vendor`).
- `linky_agents.calibration`: contar violações de diversidade entre cards e na sequência publicada, e a taxa pela definição escolhida na pergunta 1.
- Prompt do agente de curadoria (Fase 1): os sinais de lançamento grande e o reconhecimento de publieditorial entram como instruções e como casos do gold set (Fable 5.2, Bain).
