# Calibração 03: o redator v1 reescreve 4 posts do T2 (16/11/2026)

> Avaliação real da frente Post ([produção do MVP](../../ideas/producao-mvp.md)), na VPS, com os modelos de produção: redação no `claude-sonnet-5-5` (esforço baixo) e checagem no `gpt-6-luna`. Material: as pautas e as fontes do gold set (`eval/gold/2026-11-09.json` e `-10`), com padrão e público escolhidos por mim (as pautas do T2 não tinham esses campos). Nenhum texto daqui foi publicado nem mostrado a Felipe.

## Resumo

| | Rodada 1 (prompt inicial) | Rodada 2 (prompt revisto) |
|---|---|---|
| Posts | Uber, Bain, Adobe e IPO; mais Uber com opinião e Bain com ajuste | Uber, Bain, Adobe e IPO |
| Dentro de 500 a 1.300 caracteres | 4 de 6 (Uber e Adobe passaram, com até 1.532) | **4 de 4** (800 a 1.226) |
| Custo por post | US$ 0,026 a 0,058 (média 0,041) | US$ 0,026 a 0,057 (média 0,044) |
| Notas para Felipe | tamanho em 4 posts (2 acima de 1.300, 2 marcados E2 com mais de 800) | 1 problema de forma (IPO) e avisos da checagem |

- **Custo medido: US$ 0,044 por post na média, US$ 0,057 no pior caso** (redação, nova tentativa, checagem, refação e nova checagem). O alvo era até US$ 0,08. Uma redação custa de US$ 0,011 a 0,019 com o prefixo em cache (US$ 0,028 na primeira do dia, que grava o cache); a checagem, de US$ 0,0004 a 0,001.
- **Gasto total da avaliação: US$ 0,451** (teto da frente: US$ 0,50). Volume e imagem de teste apagados no fim.
- **Primeira pessoa:** nenhuma fora do lugar. Sem opinião, as leituras saíram em voz neutra. Com a opinião de teste, a leitura usou só o que a opinião dizia.
- **Fatos:** nenhum número inventado nos 10 textos. A checagem achou imprecisões reais ("quer valer" no lugar de "valeria", "no trimestre" quando a fonte não diz de quando são as corridas), e todas viraram nota.

## Leitura crítica: soa como Felipe ou como IA?

**Melhorou muito em relação ao T2,** com os mesmos fatos:
- acabou o esqueleto fixo (hook, contexto, `•`, `→`, "Onde isso gera valor", "Essa é a lição de negócio", pergunta, 3 hashtags);
- nenhuma frase de moral; 1 hashtag específica por post (o T2 usava 3, com `#Negocios`);
- a ressalva honesta aparece sempre e com forma variada na rodada 2 ("São declarações das próprias empresas, que têm interesse em defender o próprio app");
- os textos ficaram mais curtos: 800 a 1.226 caracteres, contra 1.266 a 1.400 no T2;
- os fatos vêm com atribuição ("disse ao Tecnoblog", "segundo o sócio da Bain") e com o número exato da fonte.

**O que ainda soa como IA ou não soa como Felipe:**
1. **Sem a opinião de Felipe, o post é reportagem bem-feita, não Felipe.** A leitura neutra é correta, mas impessoal ("vale perguntar o que um agente faz melhor que o seu app"). Isso é a regra do `voz.md` §3 funcionando, e mostra que **a linha de opinião no e-mail de pautas é o que mais muda a voz**. No teste com opinião, a leitura em primeira pessoa ficou natural ("Minha leitura: agente pedindo corrida ainda é solução procurando problema").
2. **Hooks que repetem fórmula.** "Usar IA virou o mínimo..." é o exemplo de H6 do playbook, copiado quase igual; "Todo mundo fala em economia agêntica" é clichê. Os bons hooks são os de número e contraste ("Quatro corridas.", "US$ 104 bilhões.", "95% das empresas brasileiras usam IA. Só 40% escalaram um caso.").
3. **Detalhe sobrando no corpo.** O redator gosta de incluir o fato lateral curioso (a assistente da DiDi que pede "um carro em que caiba o meu cachorro", a crítica do cofundador da Figma ao MCP). Isso estourava o tamanho na rodada 1. A regra "uma ideia por post" e o teto por parte cortaram parte disso, mas não tudo.
4. **Tiques que vinham do exemplo do prompt:** "Sim ou ainda não?" no fim da pergunta e "Uma ressalva:" em todo post (rodada 1). O prompt agora pede para não copiar essas frases. **Isso não foi medido de novo**, porque o orçamento da avaliação acabou.
5. **Lista com rótulo em cada item** (IPO, rodada 2: `→ Receita de nove meses: US$ 33,2 bilhões`). A validação pegou o problema, a nova tentativa não resolveu, e o aviso ficou nas notas.
6. **Detalhe de forma:** a menção entrou dentro do nome do evento ("Na @Adobe MAX"). O LinkedIn mostra o texto certo, com "Adobe" clicável.

**Veredito:** pronto para o MVP com Felipe aprovando cada post. O texto não tem as marcas de IA do T2. O que ainda falta é a voz pessoal, e ela depende da opinião que Felipe manda na pauta. Os pontos 2 a 4 vão para o ciclo de melhoria de segunda.

## O que mudou entre as rodadas

| Problema na rodada 1 | Mudança |
|---|---|
| 2 de 6 textos acima de 1.300 caracteres mesmo depois da nova tentativa, e os outros quase todos acima de 1.100 | O prompt passou a dar um teto por parte (corpo até 550 caracteres, leitura até 250, cauda até 250). A mensagem da nova tentativa diz quantos caracteres cortar e o tamanho de cada parte |
| O redator marca E2 (até 800 caracteres) e escreve E1 | Um E2 com mais de 800 caracteres passa a ser marcado como E1, sem nova tentativa: a marcação existe para a medição do playbook (§8) |
| "Para quem decide:" e "O ponto que importa:" em toda leitura; "Uma ressalva:" em toda cauda | Pelo menos uma leitura sem rótulo; a ressalva muda de forma |
| Citação deixada em inglês (Adobe) | Citação em outra língua vai traduzida |
| Hook H3 e leitura de Felipe com a mesma frase (teste com opinião) | Um anuncia e o outro desenvolve |
| A checagem marcou como "grave" teses e leituras (Uber, rodada 2), o que gerou uma refação inútil | O prompt da checagem diz que leitura e hook de tese são análise. "Grave" fica só para erro de fato. Rechecados os 4 rascunhos: as falsas graves sumiram, e ficou só o "quer valer" do IPO |
| A menção podia sair duplicada, e o serviço junta o texto com `compose_text` sem passar pelo redator | A menção vai nos 3 hooks quando os 3 citam a empresa, senão uma vez no corpo. Qualquer combinação de hook e leitura tem exatamente uma |

## Decisões tomadas pelo padrão (registradas aqui)

- **Cadeia da redação:** `claude-sonnet-5-5` (esforço baixo) e, de reserva, `gpt-5.4-mini`. **Checagem:** `gpt-6-luna` e, de reserva, `deepseek-flash`, para nunca checar o Sonnet com a Anthropic. A VPS não tem chave da DeepSeek, então hoje a reserva da checagem só falha e o post segue com a nota "a checagem não rodou".
- **Limites de entrada** da redação e da checagem: 14 mil tokens, com fontes de até 1.600 tokens cada (3 fontes cabem com o prompt).
- **Validação reprovada duas vezes:** o post não é perdido. Vai com o problema nas notas, e Felipe decide no e-mail.
- **Tamanho:** o mínimo (500) é medido no texto que o leitor vê; o máximo (1.300) no texto enviado, com a marcação da menção (cerca de 35 caracteres a mais).
- **Lista de cortes em código:** uma ocorrência já reprova. "Navegar" e "ecossistema" ficaram só no prompt, porque têm sentido técnico legítimo (agente que navega na web).
- **Ajuste:** o redator recebe o post anterior, o pedido mais recente e os anteriores, e muda só o que foi pedido. No teste ("mais curto, pergunta de escolha"), o post da Bain caiu de 1.172 para 686 caracteres e manteve hook, fatos e ressalva.

## Os textos da rodada 2

Os 4 rascunhos como Felipe os receberia. O texto padrão mostra a menção no formato little, onde ela fica; nos hooks e nas leituras alternativas, o nome aparece simples. Para comparar, os posts aprovados do T2 estão em `eval/gold/` (Uber e Bain em `2026-11-09.json`, Adobe e IPO em `2026-11-10.json`).

As notas são as que a rodada 2 gerou, com o prompt de checagem antigo. Com a checagem revista, a nova conferência dos mesmos rascunhos deu: Uber e Bain sem problema; Adobe com os mesmos 2 avisos leves; IPO com 1 grave ("quer valer", o certo é "valeria") e 1 leve. A nota de tamanho do E2 da Bain também não aparece mais: o post passa a ser marcado como E1.

### Uber (P2, gestor)

Custo: US$ 0,0533. Estrutura E1, fechamento escolha, tamanho 936 a 962. Manchete da imagem: "Agentes pediram só 4 corridas na Uber".

Texto padrão (hook 0 + leitura 0), como vai no e-mail:

```
Quatro corridas.
Foi o que agentes de IA externos pediram na Uber no trimestre.

A @[Uber](urn:li:organization:1815218) informou, na divulgação de resultados do 3º trimestre, que só quatro viagens foram pedidas por agentes de IA externos, como os do ChatGPT ou do Claude.

A DiDi, dona da 99, diz algo parecido. O vice-presidente sênior Stephen Zhu disse ao Tecnoblog que o volume é "insignificante" e perguntou: qual valor adicional um agente cria? Traz mais conveniência?

O app da DiDi já tem assistente própria, a Xiao Di, que escolhe entre 90 opções de serviço. Pedidos assim acontecem, mas Zhu não os classificou como de agentes externos.

Antes de preparar a empresa para ser comprada por agentes, vale perguntar o que um agente faz melhor que o seu app. Por enquanto, o valor está na IA dentro do produto.

São declarações das próprias empresas, que têm interesse em defender o próprio app.

Você investiria primeiro na IA do seu produto ou na abertura para agentes?

#AgentesDeIA
```

Os outros hooks:

- H6: Todo mundo fala em economia agêntica. Na Uber, agentes de fora pediram só 4 corridas.
- H5: O valor da IA ainda está dentro do seu app, não num agente de fora.

A outra leitura:

- A conta: adaptar o produto a agentes de fora é investimento sem demanda comprovada. IA no próprio app, onde o cliente já está, tem retorno mais fácil de medir.

Notas que Felipe veria:

- A refação pedida pela checagem não passou na validação; ficou o rascunho anterior
- Checagem (grave): hook, "pediram na Uber no trimestre": A fonte diz que a Uber revelou o número durante a divulgação de resultados do terceiro trimestre, mas não informa que as quatro viagens ocorreram nesse trimestre.
- Checagem (grave): hook, "O valor da IA ainda está dentro do seu app": A fonte relata poucas solicitações por agentes externos e descreve a IA própria da DiDi, mas não afirma que o valor da IA está dentro do app.
- Checagem (grave): reading, "tem retorno mais fácil de medir": As fontes não comparam a facilidade de medir o retorno da IA no próprio app com a abertura para agentes externos.

### Bain (P2, gestor)

Custo: US$ 0,0397. Estrutura E2, fechamento experiencia, tamanho 806 a 900. Manchete da imagem: "Todo mundo usa IA, poucos escalaram".

Texto padrão (hook 0 + leitura 0), como vai no e-mail:

```
95% das empresas brasileiras usam IA. Só 40% escalaram um caso.

A pesquisa da @[Bain & Company](urn:li:organization:2114) sobre o Brasil, divulgada em agosto, mostra alguma IA em 95% das empresas. Só 40% dizem ter escalado ao menos um caso de uso.

Mesmo entre essas, nem todas conseguem medir o impacto em dinheiro, e menos ainda atribuir ROI.

O que separa os grupos, segundo o sócio da Bain Lucas Brossi, é o comprometimento da liderança: onde a IA é prioridade da diretoria, o índice de escala é nove vezes maior.

Usar IA deixou de ser o critério. A pergunta que sobra é qual processo mudou e quanto custo ou receita mudou junto com ele.

São respostas das próprias empresas a uma consultoria, não uma medição independente de resultado.

Na sua empresa, algum caso de IA já tem o retorno medido em reais?

#InteligenciaArtificial
```

Os outros hooks:

- H2: Nove vezes.
É quanto a escala de IA é maior onde a diretoria trata o tema como prioridade.
- H6: Usar IA virou o mínimo. O que falta às empresas é escalar e medir.

A outra leitura:

- Para quem decide: a diferença apontada pela pesquisa está em tratar IA como prioridade da diretoria ou como mais um projeto entre tantos. É uma decisão de gestão, antes de ser de ferramenta.

Notas que Felipe veria:

- Validação: a estrutura E2 vai até 800 caracteres e o texto chega a 900: corte, ou use E1 se o fato pede contexto
- Checagem (grave): hook, "É quanto a escala de IA é maior onde a diretoria trata o tema como prioridade.": A fonte informa que o índice de escala é nove vezes maior entre empresas que apontam IA como prioridade da diretoria do que entre as que não escalaram; não compara diretamente empresas com e sem essa prioridade.
- Checagem (leve): tail, "não uma medição independente de resultado": A fonte relata respostas das empresas e dificuldade de mensurar impacto e ROI, mas não informa se houve ou não uma medição independente dos resultados.

### Adobe (P3, builder)

Custo: US$ 0,0260. Estrutura E1, fechamento escolha, tamanho 1155 a 1226. Manchete da imagem: "Adobe abre o Photoshop para agentes de IA".

Texto padrão (hook 0 + leitura 0), como vai no e-mail:

```
O próximo usuário do seu software pode não ser uma pessoa.

Na @[Adobe](urn:li:organization:1480) MAX, em Miami, a empresa lançou um MCP local: um protocolo que deixa chatbots de fora, como ChatGPT, Claude e Gemini, usarem recursos do Photoshop, Illustrator, After Effects e Premiere. Já existiam integrações com ChatGPT e Claude, mas com acesso a poucas funções.

A vice-presidente Deepa Subramaniam disse ao TechCrunch que a Adobe ainda não sabe onde traçar a linha. Vai ver como as pessoas usam e expor mais com o tempo.

Há também um agente da Adobe que fica sempre ligado, para ter contexto do trabalho, e o Builder, ferramenta de protótipos do Firefly que entra no território da Figma, em beta fechado.

A interface do software deixa de ser só tela e botão e passa a ser também um conjunto de endpoints que um agente chama. Quem desenha produto precisa decidir o que expõe, e a própria Adobe admite que ainda não decidiu.

O MCP é recente e a Adobe não divulgou números de uso. O cofundador da Figma, Dylan Field, disse no mês passado que o MCP não é um padrão perfeito e beneficia mais os laboratórios de ponta.

O software que você constrói já tem uma porta pensada para agentes? Sim ou ainda não?

#AgentesDeIA
```

Os outros hooks:

- H1: A Adobe vende Photoshop para pessoas. Agora também abre o Photoshop para o ChatGPT e o Claude.
- H6: Ter IA dentro do app já não basta. A Adobe agora deixa a IA dos outros operar o app.

A outra leitura:

- Se o ChatGPT ou o Claude operam o Photoshop, parte da relação com o cliente passa pelo chatbot. Quem vende software precisa decidir se quer estar atrás dessa porta ou na frente dela.

Notas que Felipe veria:

- Checagem (leve): body, "com acesso a poucas funções": A fonte diz que as integrações existentes permitiam acessar algumas funções, mas não afirma que eram poucas.
- Checagem (leve): tail, "a Adobe não divulgou números de uso": A fonte não informa se a Adobe divulgou números de uso, então não é possível confirmar essa afirmação.

### IPO da Anthropic (P1, gestor)

Custo: US$ 0,0566. Estrutura E3, fechamento escolha, tamanho 1178 a 1219. Manchete da imagem: "Anthropic fatura US$ 33 bi e perde US$ 104 bi".

Texto padrão (hook 0 + leitura 0), como vai no e-mail:

```
US$ 104 bilhões.
É o prejuízo da @[Anthropic](urn:li:organization:74126343) em nove meses, para US$ 33,2 bilhões de receita.

No prospecto atualizado, a Anthropic informa receita anualizada de US$ 81 bilhões no fim de outubro. O outro lado do balanço:

→ Receita de nove meses: US$ 33,2 bilhões
→ Prejuízo líquido no mesmo período: US$ 104 bilhões
→ Compromissos de computação e infraestrutura: US$ 900,9 bilhões

A oferta é de 825 milhões de ações, entre US$ 70 e US$ 78. No topo da faixa, a empresa valeria US$ 1,404 trilhão. A estreia na Nasdaq está prevista para perto de 19 de novembro.

Em paralelo, o crédito de quem constrói data centers encareceu: o título da CoreWeave rende mais de 16%, segundo a CNBC.

Para quem decide: o prospecto deixa pública a conta de um fornecedor de IA, com prejuízo alto e compromissos de computação bem maiores que a receita. Vale saber quanto dos seus fluxos depende de um único modelo e o que você faria se as condições de contratação mudassem.

Ressalva: a Anthropic tem cerca de US$ 132 bilhões em caixa e aplicações de curto prazo. Prejuízo alto não diz se nem quando o preço vai mudar.

Se o preço do seu principal fornecedor de IA subisse 30%, sua empresa absorveria ou repassaria?

#InteligenciaArtificial
```

Os outros hooks:

- H1: A Anthropic quer valer US$ 1,4 trilhão e tem US$ 900 bilhões em compromissos de computação.
- H5: A conta da IA está ficando pública, e o prospecto da Anthropic mostra o tamanho dela.

A outra leitura:

- O que muda: com crédito mais caro para a infraestrutura, contratos de computação podem ficar menores ou mais curtos, segundo a CNBC. Para quem compra IA, o momento pede olhar prazo e dependência de fornecedor, e não só o preço de hoje.

Notas que Felipe veria:

- Validação: rótulo antes de dois-pontos no máximo uma vez no corpo (vieram 2)
- Checagem (grave): hook, "A Anthropic quer valer US$ 1,4 trilhão": A fonte informa que a empresa poderia alcançar essa avaliação se as ações fossem listadas no topo da faixa; não diz que a Anthropic quer valer esse montante.

## Os testes de opinião e de ajuste (rodada 1)

A opinião abaixo foi escrita por mim só para testar o caminho, **não é de Felipe**: "acho que agente pedindo corrida ainda é solução procurando problema; o que funciona hoje é a IA dentro do próprio app". O ajuste também é de teste: "deixe o post mais curto e troque a pergunta final por uma de escolha", aplicado sobre o post da Bain da rodada 1.

### Uber com opinião (rodada 1)

Custo: US$ 0,0371. Tamanho 1223 a 1239.

```
Quatro corridas.
Foi o que agentes de IA de fora pediram na @[Uber](urn:li:organization:1815218) no trimestre.

A Uber contou, na divulgação de resultados do 3º trimestre, que só quatro viagens foram pedidas por agentes de IA de fora, como os do ChatGPT ou do Claude. Em meio ao barulho sobre uma economia "agêntica", é pouco.

A DiDi, dona da 99, também registrou um volume "insignificante". Stephen Zhu, vice-presidente sênior da empresa, disse ao Tecnoblog e devolveu a pergunta: "Qual valor adicional é criado por um agente de IA? Traz mais conveniência, por exemplo?" Para ele, o cliente já está acostumado com o app, e é preciso ver se hesita em mudar de hábito.

A IA, porém, já roda dentro do app. A DiDi tem a Xiao Di, assistente que aceita voz ou texto e escolhe entre 90 opções de serviço. Dá para pedir "um carro em que caiba o meu cachorro". Zhu disse que essas corridas já acontecem, mas não as classificou como de agentes externos.

Minha leitura: agente pedindo corrida ainda é solução procurando problema. O que funciona hoje é a IA dentro do próprio app.

Uma ressalva: são declarações das próprias empresas, não uma medição independente do mercado.

Para quem lidera produto: o que um agente de fora faria melhor que o seu app hoje?

#AgentesDeIA
```

Hooks: H2: Quatro corridas.
Foi o que agentes de IA de fora pediram na Uber no trimestre. | H1: Agentes de IA viraram assunto global. Na Uber, pediram quatro corridas no trimestre. | H3: Pra mim, agente pedindo corrida ainda é solução procurando problema.

### Bain com ajuste (rodada 1)

Custo: US$ 0,0407. Tamanho 676 a 690.

```
Quase toda empresa brasileira já usa IA. Menos da metade escalou um caso.

A pesquisa da @[Bain & Company](urn:li:organization:2114) sobre o Brasil, divulgada em agosto de 2026, mostra que 95% das empresas usam alguma solução de IA. Só 40% dizem ter escalado pelo menos um caso de uso.

E mesmo nesse grupo, nem todas conseguem medir o impacto em dinheiro, menos ainda atribuir ROI.

O ponto que importa: usar IA deixou de ser diferencial. A pergunta agora é se o uso virou processo com resultado medido.

Uma ressalva: são números declarados pelas empresas à Bain & Company, e a fonte não detalha como o retorno foi apurado.

Sua empresa hoje está mais perto de experimentar ou de escalar?

#InteligenciaArtificial
```

Hooks: H1: Quase toda empresa brasileira já usa IA. Menos da metade escalou um caso. | H2: 95% usam IA. 40% escalaram.
Nem todas as que escalaram sabem medir o retorno. | H6: Usar IA virou o mínimo. O que separa as empresas é escalar e medir.
