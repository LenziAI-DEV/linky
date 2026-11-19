# ADR 0002: direção de arte livre dentro da identidade visual

- **Status:** aceita · **Data:** 06/11/2026 · **Decisores:** Felipe Lenzi (produto), Claude (arquitetura)

## Contexto

O motor `linky-render` tem 3 layouts (escada, contraste e tese), e o agente de direção de arte só preenche um deles. No primeiro post do T2 (Nubank), a imagem saiu idêntica em estrutura ao exemplo do Airbnb. Felipe deixou claro que **a intenção não é ter moldes**: a IA deve ter liberdade criativa para desenhar cada imagem conforme a notícia, respeitando apenas a identidade visual.

## Decisão

1. **Linguagem visual por componentes.** Os 3 layouts viram exemplos. O agente escolhe a metáfora visual da notícia e compõe livremente, sobre a grade da marca, a partir de uma biblioteca de componentes: manchete com destaque, número em destaque, pilhas de comparação, linha do tempo, antes e depois, funil, matriz 2×2, checklist, escada, equação, citação, fluxo etc.
2. **O motor é o guardião da identidade:** só tokens e fontes da marca, margens, contraste mínimo, colisão entre elementos, lima só em áreas pequenas e retícula ancorada numa estrutura. A composição é um JSON validado. Se for inválida, ela volta para o agente com o motivo.
3. **Válvula criativa:** quando nenhum componente serve, o agente pode desenhar um diagrama próprio (SVG restrito à paleta) numa área delimitada. Só nesse caso há revisão por um modelo com visão, para controlar o custo.
4. **Anti-repetição:** o registro guarda a composição de cada post, e a mesma composição não se repete num intervalo de 5 posts.
5. **A biblioteca nasce do T2, não de suposição.** Durante a semana Mágico de Oz, Claude faz a direção de arte livre de cada post à mão (`tools/t2_art/`). Cada script declara as peças que usou. No fim do T2, as peças recorrentes viram componentes do motor.

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Manter 3 moldes e criar mais moldes | Continua repetitivo, só demora mais para cansar. Não atende ao pedido |
| SVG totalmente livre escrito pelo modelo | Modelos baratos desenham mal em SVG, e a qualidade varia. Exigiria revisão com visão em todo post, com mais custo e latência |
| Imagem gerada por IA | Fora do escopo do MVP: custo, identidade inconsistente e texto mal renderizado |
| Figma no caminho crítico | Descartado no briefing (latência, dependência e custo) |

## Consequências

- **Positivas:** cada post tem uma imagem pensada para a notícia, com identidade consistente. O custo continua em centavos, porque a composição é JSON e o render é determinístico.
- **Negativas:** o motor fica mais complexo (motor de composição, verificação de colisão e de contraste). O agente de direção de arte precisa de mais contexto e talvez de um modelo um pouco melhor que o GPT-5-nano. Isso será medido no T7.
- **Implementação das proteções (etapa F, 10/11):** motor de composição, regras e registro contra a repetição no [ADR 0006](0006-motor-de-composicao.md).
- **Primeira aplicação:** o post do Nubank foi refeito com composição própria (pilhas "antes × hoje" com fantasmas, mais uma linha do tempo da função do analista), em `tools/t2_art/2026-11-06-nubank.py`.
