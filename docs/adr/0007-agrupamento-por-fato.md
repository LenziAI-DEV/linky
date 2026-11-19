# ADR 0007: agrupamento determinístico dos itens por fato antes da triagem

- **Status:** aceita · **Data:** 10/11/2026 · **Decisores:** Claude (arquitetura), a partir dos aprendizados dos dias 1 e 2 do T2

## Contexto

O coletor só deduplica por URL canônica e por título idêntico no mesmo dia. A mesma notícia, vinda de fontes diferentes (às vezes em inglês e em português), chega como vários itens: a Alexa no dia 1 do T2 (itens 10 e 13) e ~25 itens do caso do CEO da Nvidia no dia 2. Na triagem, cada item repetido é um candidato a card repetido, e o gold set já contava "top N por fato" à mão (cards do mesmo acontecimento contam uma vez).

Restrições: sem LLM (custo e determinismo; a triagem por agente vem depois do T2), sem dependência pesada (o serviço roda em 256 MB), e a interface tem de servir ao `digest` de hoje e à triagem da Fase 1.

## Decisão

1. **Novo módulo `linky_agents.stories`:** `group_stories(itens) -> list[Story]`. Um **fato** (`Story`) tem o item **representante** e as **fontes irmãs** (`GLOSSARY.md`); `Story.sources` dá as URLs para o card e `Story.to_json()` é a entrada da triagem (representante, irmãs, fontes, primeira e última publicação).
2. **Termos do título**, não do resumo: minúsculas, sem acento, sem palavras vazias em português e inglês, sem verbos de anúncio ("lança", "launches") e sem "IA/AI"; plural simples; números e valores contam ("5.2", "$11b"). Um vocabulário pequeno de notícia leva o português ao inglês (espiã → spy, investiga → investigate, processados → sue, vaza → leak...), procurado antes e depois de tirar o plural: as fontes brasileiras repetem fatos da imprensa americana.
3. **Peso pela raridade no próprio lote** (IDF). Semelhança entre dois títulos = peso dos termos em comum sobre a média geométrica do peso de cada título.
4. **Em ordem de publicação**, o item entra no fato que tem o item mais parecido com ele se: semelhança ≥ **0,30**; pelo menos **2 termos** em comum, contando uma expressão seguida nos dois títulos como um termo só ("Amazon Bedrock AgentCore", "Hugging Face", "Jensen Huang"); e o fato tem item publicado até **48 h** antes. Senão, abre um fato novo. Título idêntico é sempre o mesmo fato. A janela conta a partir do item mais recente do fato, então um caso que se desdobra todo dia continua junto.
5. **Representante:** o item mais parecido com os demais do fato; desempate pela fonte primária, depois o mais antigo. Resultado independente da ordem de entrada.
6. **`gold digest`** passa a aceitar vários arquivos e agrupa por fato (um número por fato, as irmãs com `+` e o ID, porque a triagem do gold set rotula todos os itens); `--flat` volta à lista antiga.

## Calibração (itens reais de 06 a 10/11/2026, copiados da VPS)

248 itens. Rotulei à mão 24 fatos repetidos, com 93 itens; sem agrupar, eles viram **69 cards a mais**. Resumos de notícias ("Resumo do OD") ficaram fora da conta.

| Lote | Fatos | Cards a mais que sobram | Itens no fato errado |
|---|---|---|---|
| 06 a 10/11 de uma vez | 206 (19 com irmãs, 61 itens agrupados) | 31 de 69 (−55%) | 4 |
| Um dia por vez (como na rotina diária) | 222 | 31 de 53 | 2 |

- **Caso Nvidia** (31 itens no lote de 5 dias): o maior fato junta 17, mais um de 3 (a assessoria de imprensa); 11 ficam soltos (ângulos com título próprio, como "The race is on to sue Nvidia" ou "Is Jensen Huang's job on the line?"). Num dia só (09/11), o caso domina o lote e os próprios termos perdem peso: o maior fato fica com 7.
- **Juntou certo:** Alexa (EN), Claude Code vazando segredos (EN + PT), Siri (EN + PT), lançamento do Claude Fable 5.2 (5 itens, 5 fontes, 2 idiomas), rodada da OpenAI (3 itens, 3 dias), Muse Spaces e Muse Ember separados, a mesma oferta repetida em dois dias.
- **Falsos positivos (4):** "Anthropic targets $1.4 trillion IPO" junto da rodada da OpenAI (o título da Verge sobre a OpenAI cita o IPO da Anthropic); Taxbit junto das duas partes do post da Okta (AWS); "Spotlight: espionagem, poder e chips..." junto dos chips do Google; dois itens diferentes sobre o Gemini (10/11).
- **Falsos negativos típicos:** ângulos diferentes do mesmo fato sem termos em comum (eleição americana: "Nasdaq perde US$ 2,5 tri" e "Big Tech lost big"; os 5 posts da Adobe), português sem nome próprio em comum, os 5 posts da Nvidia sobre a Coreia (3 ficam soltos), Gemini Robotics (o título da DeepMind e o da Ars dividem só o nome), os chips da Nvidia vendidos à China (EN + PT) e o gás da Anthropic ("geradores a gás" e "natural gas turbines" dividem só "Anthropic" e "gás").
- O limiar foi escolhido pela precisão: juntar dois fatos esconde uma pauta; deixar dois itens separados só repete um card, que é o que já acontece hoje. Com 0,25 sobram 26 cards a mais, mas 8 itens caem no fato errado; com 0,33, 39 e 1.
- **Limite da medida:** calibrado e medido no mesmo conjunto, com rótulos meus. Recalibrar com os dias seguintes do T2 antes de ligar a triagem por agente.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Agrupar com LLM ou embeddings | Custo por item (teto de US$ 3/mês), modelo ou dependência nova (embeddings locais pesam centenas de MB) e resultado não determinístico. Fica para depois se a triagem medir que vale |
| Ligação simples entre pares (componentes conexos) | Corrente "A parece B, B parece C": juntava Muse Spaces com Muse Ember e a rodada da OpenAI com o relatório da Ramp. Entrar pelo item mais parecido, em ordem de publicação, corta a maior parte |
| Comparar com a soma do fato (centroide) | O vetor do fato cresce e dilui: juntou bem menos na calibração (no mesmo limiar, só os pares mais óbvios) |
| Usar o resumo além do título | Mais termos em comum entre fatos diferentes: piorou nos dois sentidos |
| Janela de 72 h | Mais falsos positivos sem ganho no caso Nvidia, que se renova todo dia |

## Consequências

- **Positivas:** a triagem passa a ver fatos, não itens; o card ganha as fontes irmãs de graça. Puro Python, testável (`tests/test_stories.py`), sem custo.
- **Negativas:** o vocabulário PT → EN é uma lista à mão (20 e poucos termos de notícia) e vai precisar crescer; a raridade depende do lote, então um caso enorme num dia só se agrupa pior do que no lote de vários dias. A data do fato para a validade da pauta continua sendo decisão da curadoria (`Story.first_seen` e `last_seen` ajudam).
