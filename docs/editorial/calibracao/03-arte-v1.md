# Calibração 03: agente de arte v1 (16/11/2026)

Avaliação real do agente de direção de arte (`linky_agents.agents.art.make_image`, prompt `prompts/arte/v1.md`) na VPS, com a imagem de teste da frente Imagem (`linky-agents:imagem`) e os limites do serviço em produção: raiz somente leitura, `/tmp` de 16 MB, 256 MB de memória sem swap, meia CPU, 64 processos, volume de teste próprio (`linky_imagem_teste`).

**Material:** 4 posts do T2 do gold set (`eval/gold/2026-11-09.json` e `-10`), com a pauta do card (título, fato, ângulo e fontes) e o texto final aprovado por Felipe no lugar do rascunho. A ideia central (`draft.headline`) é o título do card, porque o gold set não tem a manchete do redator. Uber e IPO da Anthropic ficaram de fora: são os dois exemplos do prompt. Script: `tools/eval_arte.py`.

| Post | Padrão | Imagem do T2 (feita à mão) |
|---|---|---|
| Claude Code vaza senhas (11/11) | caso | janela de terminal, arquivo e repositório |
| Cotas de IA (11/11) | tese | três medidores de cota |
| Adobe para agentes (12/11) | lançamento | diagrama de passagem |
| Bain, IA no Brasil (13/11) | pesquisa | funil em barras e "9×" em bloco |

## Resultado

**4 de 4 imagens válidas** na rodada final (Haiku 5.5, esforço médio), as 4 com tema alternado pelo registro (claro, escuro, claro, escuro). Todos os números e frases das imagens estão no post (conferido um a um).

| Post | Propostas | Custo | Tempo | Veredito |
|---|---|---|---|---|
| [Claude Code](03-arte-v1/2026-11-11-claude-code-segredos.png) | 1 | US$ 0,0023 | 14 s | Boa. 2.539 contra 501 em escala real, 1.994 e 63 em colunas. Repete na barra o número da manchete. |
| [Cotas](03-arte-v1/2026-11-11-cotas-de-ia.png) | 1 | US$ 0,0026 | 19 s | A melhor. "3" gigante no bloco que sangra e os três preços ao lado: lê-se em 2 s. |
| [Adobe](03-arte-v1/2026-11-12-adobe-agentes.png) | 3 | US$ 0,0060 | 46 s | Boa no diagrama. A legenda de cores embaixo (violeta "já funciona", lilás "em teste") não corresponde a nada no esquema. |
| [Bain](03-arte-v1/2026-11-13-bain-brasil.png) | 2 | US$ 0,0031 | 26 s | Aceitável. Barras em escala real e o 9×, mas sobra um vão entre as barras e o fio. A nota do rodapé ("barras em escala real") é metalinguagem. |

As recusas que voltaram ao agente e foram corrigidas sozinhas: retícula desenhada sobre o rodapé, manchete longa demais para 2 linhas e esquema começando a 180 px da manchete (Adobe e Bain).

As composições (JSON), o texto alternativo e o relatório de cada execução estão em [`03-arte-v1/`](03-arte-v1/).

## Rodadas e escolha do modelo

| Rodada | Modelo | Válidas | Custo | O que aconteceu |
|---|---|---|---|---|
| 1 | gpt-6-luna, raciocínio baixo | 4 de 4 | US$ 0,0049 | Claude Code com metade de baixo vazia; cotas sem número, só lista com rótulos soltos; Bain desalinhado da margem (x 100). Barra lilás com texto branco (defeito do componente). |
| 2 | gpt-6-luna, raciocínio baixo | 3 de 4 | US$ 0,0047 | Depois da regra de espaço e do prompt reforçado: cotas melhorou (três preços grandes); Claude Code com buracos entre as barras. Adobe caiu num erro meu (manchete que não cabia virava exceção em vez de motivo). |
| 2 | claude-haiku-5-5, esforço médio | 3 de 4 | US$ 0,0110 | Visivelmente melhor nas três: "501" gigante, preços grandes, Bain em colunas de altura proporcional. Mesmo erro meu no Adobe. |
| final | claude-haiku-5-5, esforço médio | 4 de 4 | US$ 0,0140 | Com as correções. |

**Decisão:** a cadeia `arte` em `config/models.yaml` passa a começar no **Haiku 5.5 (esforço médio)**, com o **gpt-6-luna (raciocínio baixo)** de reserva. O Haiku custa o dobro do luna e ainda fica em **~US$ 0,0035 por imagem** (média da rodada final; até US$ 0,006 com 3 propostas), cerca de US$ 0,08 por mês em 22 posts.

**Gasto total da avaliação:** US$ 0,0346 (ledger do volume de teste; 24 execuções do agente), dentro do teto de US$ 0,50 da frente.

## O motor dentro do serviço

- O `Dockerfile` copia `assets/brand/tokens.json` e as 6 fontes Barlow (com a licença OFL), e fixa `LINKY_ASSETS=/app/assets`. As fontes de exploração (Inter, JetBrains Mono, Space Grotesk) ficam fora da imagem.
- Render sem modelo (`tools/eval_arte.py render`, os 2 exemplos do prompt): 2,9 s, **pico de 66 MB de RSS** (cgroup: 48 MB). Os PNGs do container são **idênticos byte a byte** aos gerados no PC.
- Avaliação completa (harness, chamadas HTTP e motor no mesmo processo): **pico de 71 MB de RSS** (cgroup: 62 MB). Cabe com folga nos 256 MB do serviço; nada escreve em `/tmp`. **Nenhum ajuste de limite é necessário.**
- Tempo: 1,5 s de motor por imagem; o resto é o modelo. `make_image` leva de 12 a 46 s (1 a 3 propostas). A rota que a chama precisa de timeout de pelo menos 90 s.

## O que entrou no código por causa da avaliação

1. **Regra de espaço** no laço (`art.space_reasons`): esquema que termina antes de y 1000 ou começa a mais de 170 px da manchete volta ao agente com o motivo. Não é regra da marca (o motor aceita); é direção de arte.
2. **`bleeding_bars`** escreve em tinta dentro de barra lilás (antes, branco: 1,84:1). Os scripts do T2 seguem gerando os mesmos PNGs.
3. **Prompt:** princípios "ocupa a tela" e "alinhado", comparação de grandezas por barras ou números gigantes, e a linha do cartão `@superficie` na tabela de contraste (`@apoio` sobre o cartão escuro, 3,7:1, foi o erro mais repetido dos dois modelos).
4. **Manchete que não cabe** volta como motivo, não como erro.

## Para a v2 (ciclo de segunda, com o uso)

- Legenda só para cor ou forma que aparece no esquema (Adobe).
- Não repetir no esquema o número que a manchete já diz (Claude Code e Bain); a manchete diz a tese e o esquema mostra a escala.
- `source_note` só para ressalva sobre o fato ("teste não confirmado"), nunca sobre o desenho.
- Metáforas próprias da notícia, como no T2 (janela de terminal, medidores de cota), ainda aparecem pouco: o agente prefere números e barras. Um terceiro exemplo no prompt, de metáfora sem número, pode abrir esse caminho.
- Logos oficiais das empresas (o guia pede o logo no topo; hoje só o nome em Barlow Bold).
