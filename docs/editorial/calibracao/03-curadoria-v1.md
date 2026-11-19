# Calibração 03: curadoria v1 no gold set (16/11/2026)

> Frente Pautas da produção do MVP. Modelo de verdade (gpt-6-luna) na VPS, imagem de teste `linky-agents:pautas`, volume `linky_pautas_teste`. Script: `python -m linky_agents.agents.pautas_eval` (reproduz cada dia do gold set com os mesmos itens da triagem do T2 e exclui os cards dos dias anteriores).

## Resultado (rodada 3, a arquitetura final)

| Dia | Escolhas | No top 3 | No top N (N = cards do dia no gold set) | Custo |
|---|---|---|---|---|
| 06/11 (3 cards) | 1 | 1 (Nubank em 1º) | 1 | US$ 0,0034 |
| 09/11 (lote de 4 dias, 128 fatos, 5 cards) | 5 | 1 (Claude Code em 1º) | 1 | US$ 0,0106 |
| 10/11 (4 cards) | 2 | 1 (IPO da Anthropic em 1º) | 2 (Adobe em 4º) | US$ 0,0061 |
| **Total** | **8** | **3 (38%)** | **4 (50%)** | **US$ 0,0067 por dia** |

- **Meta de 80% não atingida.** Atenção à conta: contando por escolha com corte no top 3 (pergunta 1, opção a), o máximo possível neste gold set é 6 de 8 (75%), porque o lote de 09/11 tem 5 escolhas. E a Bain (patrocinada) deve cair pela v1, então o teto real no top N é 7 de 8.
- **Custo:** US$ 0,0067 por dia em média, bem abaixo do alvo de US$ 0,03 (o lote de 4 dias custou US$ 0,0106). Gasto total da avaliação: ~US$ 0,07 (4 rodadas), dentro do teto de US$ 0,50.
- Os cards de 06 e 10/11 batem quase todos com os do T2 (Nubank e Ramp; IPO, Gemini saúde, DeepMind/Signal, Adobe).

## O que falha (dia 09/11)

Posições por nota: Fable 9º (27 pts), Uber/99 8º (28), cotas (Apple) 18º (24), Bain 16º (25, deveria ser eliminada como patrocinada, mas o resumo do item não diz que é). No topo ficaram fatos de uma fonte só (captação da OpenAI "reportedly", Muse Ember, relatório sobre a Anthropic). Causas:
1. **O tema "cotas" do T2 juntava 3 empresas** (Apple, Google, Samsung) num card de tese; aqui são 4 fatos separados, cada um com nota média.
2. **Notas pouco espalhadas** num lote de 60 candidatos (2 chamadas de 30): quase tudo entre 23 e 31.
3. O sinal que mais prevê a escolha de Felipe é o **tamanho do fato** (fontes independentes, imprensa brasileira), e a rubrica v1 não tem peso para isso (pesos mantidos pela pergunta 7).

## Arquitetura que ficou (e por quê)

- Rodada 1 (lotes de 5 na curadoria, texto do card junto): 4/8, mas a curadoria deixava fatos fortes "sem padrão" por falta de número no resumo e eliminava matéria de imprensa por "falta de confirmação independente".
- Rodada 2 (prompt menos rígido): 2/8. Notas em lotes de 5 não são comparáveis (quase tudo 2 e 3).
- Rodada 3: **curadoria comparativa** (até 30 fatos por chamada), `same_as` para juntar o mesmo fato que o agrupamento separou, e um **terceiro agente, `pauta`** (`prompts/pauta/v1.md`), que escreve o texto só dos cards escolhidos (+2 reservas). Haiku 5.5 entrou como última reserva da triagem, da curadoria e da pauta, porque a chave da DeepSeek não está na VPS.

## Próximos passos sugeridos (não feitos)

1. Decidir com Felipe um critério de **tamanho do fato** (fontes independentes / repercussão no Brasil) ou subir o peso de Brasil: é o ajuste que mais deve mexer no dia 09.
2. Curadoria numa chamada só nos lotes grandes (subir `CURATION_BATCH` para 60 e o limite de entrada), para notas comparáveis no domingo.
3. Agrupamento (`stories.py`, ADR 0007): o IPO de 10/11 veio em 4 fatos; o `same_as` só juntou 3 pares no dia 09.
4. Ressalva: os casos de calibração do prompt (Nubank, Fable, Bain, Greenlight) vêm do próprio gold set, então a avaliação é otimista. A medida que vale daqui para frente é a das escolhas reais de Felipe a partir de 19/11.
