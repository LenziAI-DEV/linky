# Calibração do fim do T2: leitura preliminar (11/11)

> **Preliminar.** Feita na quarta 11/11 com os 3 dias do gold set (06, 09 e 10/11) e os itens coletados até 11/11 21:17 UTC. Na sexta 13/11, rodar de novo (abaixo) e conferir se algo mudou. **Nenhuma fonte foi podada e nenhum peso foi mudado:** as decisões são de Felipe. Números completos em [`02-fim-do-t2-dados.md`](02-fim-do-t2-dados.md). Proposta de rubrica v1 em [`../rubrica.md`](../rubrica.md#rubrica-v1-rascunho).

## Como rodar de novo na sexta

1. Copiar os itens da VPS (só leitura) para uma pasta temporária, fora do repositório:
   `scp 'vps:~/linky-dev/data/items/*.jsonl' <pasta>/`
2. Se houver dia novo no gold set (`eval/gold/AAAA-MM-DD.json`), validá-lo antes com `uv run python -m linky_agents.gold check <arquivo>`.
3. Gerar o relatório:
   `uv run python -m linky_agents.calibration <pasta>/*.jsonl --out docs/editorial/calibracao/02-fim-do-t2-dados.md`
   (padrões: `--gold eval/gold`, `--sources sources/sources.yaml`; sem `--out`, imprime na tela).

Até sexta não deve entrar dia novo no gold set (os 6 posts da semana já estão escolhidos), então o que muda é só a coluna "coletados". A taxa de escolha no top 3 só muda se Felipe pedir pautas novas.

## 1. Escolha no top 3: 6 de 8 (75%), abaixo da meta de 80%

| Dia | Escolhas | No top 3 | As que ficaram de fora |
|---|---|---|---|
| 06/11 | 1 | 1 | — |
| 09/11 (lote) | 5 | 3 | **Fable 5.2** (pedido fora dos cards, posição 4, 27/33, empatado com o card 3 e perdeu no desempate) · **Bain Brasil** (card 4, posição 6, 26/33) |
| 10/11 | 2 | 2 | — |

Leitura:
- **Fable:** a falha foi de julgamento, não de peso. O item teria 27/33, mas eu o tirei dos cards como "guerra de torcida entre modelos". A rubrica v1 resolve com o caso "lançamento grande com ângulo de capacidade" (não com mais peso).
- **Bain:** entrou porque o T2 acelerado abriu mais horários do que fatos fortes no lote. Ficou em 6º e era **conteúdo patrocinado pela Bain** na MIT Technology Review Brasil. Com o filtro de publieditorial da v1, nem seria card.
- **Por dia**, a conta depende da definição (pergunta 1 da rubrica v1): 2 de 3 dias com todas as escolhas no top 3, ou 3 de 3 dias se a regra for "pelo menos uma escolha no top 3". Em lote com 5 escolhas, só 3 cabem no top 3 por construção.
- A amostra é pequena (3 dias, 8 escolhas). Uma escolha a mais ou a menos move a taxa em ~12 pontos.

## 2. Fontes: o que gerou pauta

- **Geraram post:** verge-ai, techcrunch-ai, canaltech, tecnoblog, olhar-digital, hn-ai-100, ars-ai e mit-tr-br. A imprensa (EUA e Brasil) carrega a curadoria; as brasileiras aparecem em 6 dos 8 posts (Nubank, Claude Code, cotas, Uber, Bain e IPO).
- **Geraram card, mas não post:** aws-ml (Greenlight, dia 1), wired-ai, deepmind e google-ai (dia 3).
- **Primárias quase não viram card:** openai (5 relevantes em 10 triados, nenhum card; 1 eliminado como publieditorial e 1 por bloqueio 403), nvidia (0 relevante em 7: Coreia, robótica, 6G), huggingface e google-research (nada relevante). Os lançamentos que viraram post chegaram pela imprensa, que já traz o contexto.

## 3. Candidatas à poda (para decidir com Felipe)

| Fonte | Sugestão | Por quê |
|---|---|---|
| **simonwillison** (probation) | podar | 0 relevante em 10 triados; blog pessoal de dev, fora do território |
| **nvidia** | podar | 0 relevante em 7 triados; institucional e nicho (o filtro de palavra-chave não ajuda num blog que só fala de IA) |
| **microsoft-source-ai** (probation) | podar ou trocar o feed | 0 item no período: o feed responde (10 entradas), mas nada novo em 7 dias (todas descartadas como antigas) |
| **mit-smr-ai** | podar ou trocar o feed | igual: 20 entradas no feed, nenhuma nova no período |
| **aws-ml** (probation) | manter em observação ou podar | 4 relevantes em 15, mas 9 dos 11 descartes são tutorial ou campanha do fornecedor; o único card (Greenlight) é caso de cliente publicado pelo fornecedor, o que a v1 trata como publieditorial. Era candidata desde o dia 1 |
| **huggingface**, **google-research** | observar | 0 relevante, mas poucos triados (4 e 1) |
| **openai** | manter | 50% relevantes; não vira card porque bloqueia leitura (403) e a imprensa cobre os mesmos fatos. Útil como fonte primária para conferir números |
| **hbr**, **mckinsey** | manter, decidir o papel | relevantes (100% e 50%), mas são análise, não fato do dia: o filtro "aconteceu ontem" os elimina. Talvez sirvam para o post de tese, não para o card diário (pergunta 6 da rubrica v1) |
| **mit-tr-ai** | observar | 0 relevante em 4 |

Também no relatório: hn-ai-100 (probation) gerou 1 post como fonte irmã do IPO, e olhar-digital (probation) gerou card e post. As duas podem sair de probation.

## 4. Observações para a sexta

- Alguns itens aparecem duas vezes na triagem com IDs diferentes (ex.: "Control Room" da OpenAI e o tutorial Okta da AWS), provavelmente o mesmo link coletado com URL diferente. Não muda a leitura, mas infla "coletados" e "triados" dessas fontes em 1 ou 2.
- No dia 3, um item do IPO (techcrunch-ai, `4f4fd1b1…`) não foi agrupado no card 1 e aparece no ranking como fato separado. O agrupamento por fato (etapa H) não existia quando o dia foi registrado.
