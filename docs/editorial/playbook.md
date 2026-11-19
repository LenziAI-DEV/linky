# Playbook editorial (v2, aprovado por Felipe em 16/11/2026)

> **Em vigor desde 16/11/2026.** Sai do laboratório editorial (direção aprovada em 13/11). É a segunda fonte do agente redator, ao lado do [`voz.md`](voz.md).
>
> **Divisão de papéis:**
> - O `voz.md` guarda as **regras fixas**: posicionamento, público, fatos, primeira pessoa, tom e vocabulário. Só Felipe muda.
> - Este playbook guarda **o que se testa**: pautas, hooks, estruturas, fechamento e imagem. O sistema pode mudá-lo sozinho, dentro das regras da §9. Cada mudança fica registrada na §11 e aparece no relatório mensal, e Felipe pode desfazer qualquer uma.

## 1. O que os dados dizem (ponto de partida)

| Achado | Fonte | Consequência |
|---|---|---|
| Os posts pessoais de Felipe rendem mais que os do linky (448 e 307 impressões contra uma mediana de ~204, e são os únicos com comentários) | Linha de base de 13/11 | A opinião ou a experiência de Felipe é o miolo do post (§4) |
| Nenhum post do linky gerou comentário; as perguntas abertas não funcionaram | Linha de base de 13/11 | Pergunta fácil: de escolha ou para um público nomeado (§6) |
| Dois ou três posts no mesmo dia se canibalizam (23, 217 e 75 impressões na quinta) | Linha de base de 13/11; FlyPost (−10%) | **Um post por dia, nunca dois** (§10) |
| Primeira pessoa +19%, história +33%, detalhe concreto +15%; pergunta na abertura −17% | FlyPost, 116 mil posts, comparando cada autor com ele mesmo | Tipos de hook da §3 |
| Texto com cara de IA rende ~22% menos que o mesmo autor | LigoSocial | Variar a estrutura; lista de cortes da §7 |
| 3 ou mais hashtags −8%; "comente X" −24% desde jul/2026; link no corpo −13% | FlyPost; LinkedIn (mar/2026) | 0 a 1 hashtag, nenhuma isca, nenhum link |
| Contraste de preço viaja fora da rede (~30 mil impressões); comunidade e história engajam (84 e 62 reações) | Perfil do Leonardo, 18 posts | Padrões de pauta da §2 |

Tudo isso é **sinal, não lei**: a amostra de Felipe tem 11 posts. A §9 diz como os números das próximas semanas mudam este playbook.

## 2. Escolha da pauta: padrão antes da notícia

A rubrica (`rubrica.md`) continua decidindo se a notícia é boa. Este playbook acrescenta a pergunta **"em que padrão ela cabe?"**. Uma notícia que não cabe em nenhum padrão vai para o banco, mesmo com nota alta.

| Padrão | O que é | Exemplo | Estado |
|---|---|---|---|
| **P1. Contraste de custo** | Um lançamento com um número de preço, tempo ou escala que muda a conta de uma empresa | "Uma tarefa de código resolvida por US$ 0,20." | ativo |
| **P2. Número com virada** | Um número forte com uma segunda metade que o contradiz ou o qualifica | "O iFood criou 27 mil agentes de IA em 10 meses. Só 200 têm impacto relevante em escala." | ativo |
| **P3. Empresa conhecida, caso concreto** | Uma empresa que o leitor conhece (de preferência brasileira) fazendo algo específico com IA | "Na Vale, reunião está virando código." | ativo |
| **P4. Risco com ação** | Um risco prático de IA com o que fazer na segunda-feira | "A IA pode entrar na sua conta sem receber sua senha." | ativo |
| **P5. Bastidor de quem constrói** | Algo que Felipe viu ou fez construindo agentes (só com o material dele, `voz.md` §3) | "Nos agentes que construo, o gargalo nunca foi o modelo." | ativo (depende de Felipe) |
| **P6. Comunidade e evento** | Liga, eventos, pessoas: pessoal, com foto | o post do Talks da Liga | ativo (só por pedido, ADR 0008) |

Mais três regras para a pauta:
- **Um público por post.** O card diz para quem é: gestor, builder ou estudante. O post fala com esse leitor, e os outros dois entendem sem esforço (`voz.md` §2).
- **Valor antes de lançamento.** Lançamento só entra com o ângulo de capacidade ou de custo (rubrica v1, "lançamento grande").
- **O card leva:** padrão, notícia, público e ângulo (uma frase com a tese possível).

Padrões novos vêm da base de referências (`eval/referencias/`, outliers de 5x ou mais a mediana do próprio autor) e entram como **em teste** (§9).

## 3. Hooks

O hook é a primeira linha, e precisa funcionar antes do "ver mais".
- No celular, o LinkedIn mostra cerca de 140 caracteres antes de cortar.
- **Regra:** o hook tem até 120 caracteres. Ele pode ganhar uma segunda linha de apoio, e as duas juntas não passam de 200.

**O redator escreve 3 hooks de tipos diferentes, e Felipe escolhe um no e-mail de aprovação** (ou reescreve). O hook escolhido e o tipo dele ficam registrados (§8).

| Tipo | Como é | Exemplo | Quando |
|---|---|---|---|
| **H1. Contraste concreto** | Dois fatos lado a lado que não combinam | "Quase toda empresa brasileira já usa IA. Quase nenhuma sabe quanto ela rende." | P2, P3; o padrão |
| **H2. Número seco** | O número sozinho, sem adjetivo, e a virada na linha de baixo | "Quatro corridas." | P1, P2 |
| **H3. O que eu vejo** | Primeira pessoa com um fato de Felipe | "Nos agentes que construo, o gargalo nunca foi o modelo." | Só com a opinião ou a experiência de Felipe |
| **H4. Cena** | Um momento concreto, com lugar e ação | "Terça, 22h, o agente parou no meio do pedido." | Só com experiência real de Felipe (P5, P6) |
| **H5. Afirmação seca** | Uma tese curta, sem "eu acho" | "Software que não conversa com agentes vai virar etapa manual." | P3, P4 |
| **H6. Contra a corrente** | Contradiz o que o mercado está repetindo, com base no fato | "Usar IA virou o mínimo. O diferencial agora é medir." | Quando o fato sustenta |

**Evitar no hook:**
- pergunta na abertura ("Você já pensou...?");
- "opinião impopular", "ninguém está falando sobre isso" e outras promessas vazias;
- número de terceiros sem virada ("95% das empresas...", e para por aí);
- nome do veículo ("Segundo a MIT...");
- dois-pontos de suspense ("O motivo:");
- emoji.

## 4. Estruturas

A estrutura muda conforme o padrão. **Nenhum bloco é obrigatório em todas.** O que se repete em todos os posts são as regras do `voz.md`.

### E1. Análise (o padrão para notícia: P1 a P4)

| Parte | Regra |
|---|---|
| Hook | §3 |
| Acompanhamento | 1 a 2 frases que sustentam o hook com o fato (quem, o quê, quando) |
| A empresa em uma frase | Só se o leitor pode não conhecer: "A X faz Y para Z." |
| O que aconteceu | Prosa curta em 1 a 2 parágrafos. Lista com `•` só se houver 3 ou mais itens paralelos de verdade |
| **Minha leitura** | A opinião de Felipe, marcada como dele ("Minha leitura:", "Pra mim, o ponto é..."). Ver a regra abaixo |
| Ressalva honesta | Uma frase sobre o limite do fato: "são números da própria empresa", "ainda não há teste independente", "vale para quem já tem dado organizado" |
| Fechamento | §6 |

**Sem a opinião de Felipe, não há "Minha leitura".**
- O e-mail de aprovação mostra duas leituras possíveis, em voz neutra, para Felipe escolher ou reescrever.
- Se ele aprovar sem escolher, o bloco sai em voz neutra ("O ponto que importa:"), nunca em primeira pessoa (`voz.md` §3).

### E2. Número com virada (P1, P2, em formato curto)

Hook com o número (H2) → a virada → por que o número engana ou importa → leitura → ressalva → pergunta. De 500 a 800 caracteres, sem lista.

### E3. Comparação (antes e depois, X contra Y, preço contra preço)

Hook com o contraste → as duas pontas em 2 linhas cada (lista com `•`, ou `→` para antes e depois) → o que muda para quem decide → leitura → pergunta de escolha ("custo ou confiabilidade?").

### E4. Relato (experiência: P5 e o pedido do tipo experiência)

É o formato de relato do `voz.md` §6.1, sem mudança. Fonte única: Felipe.

### E5. Comunidade (P6)

Hook com a cena ou o resultado do evento → quem estava e o que aconteceu → o que Felipe levou dali (só o que ele disse) → agradecimento ou menção às pessoas que ele citou → sem pergunta, ou uma pergunta para quem esteve lá. Imagem: as fotos de Felipe (até 9, ADR 0008), não a arte da marca.

**Tamanho:** de 600 a 1.300 caracteres (o E2 fica entre 500 e 800). Mais curto é melhor quando o fato é simples.

## 5. Formato do texto

- **Parágrafos de 1 a 3 linhas**, com linha em branco entre eles.
- **Listas só quando os itens são paralelos de verdade.** Nada de lista em todo post. No máximo uma lista por post.
- **Rótulo antes de dois-pontos** ("O atalho: ...", "A brecha: ...") no máximo uma vez por post.
- **Menção à empresa principal** com `@` na primeira vez que ela aparece (formato little, `voz.md` §7).

## 6. Fechamento

- **Pergunta fácil de responder.** Pode ser:
  - de escolha: "Você aposta no melhor modelo ou no melhor ecossistema?";
  - para um público nomeado: "Para quem lidera time de dados: qual foi o primeiro caso que vocês mediram?";
  - de experiência curta: "Qual ferramenta de IA já entrou no seu dia de trabalho?".
- **Proibido:**
  - "o que vocês acham?";
  - "comente X que eu te mando";
  - "concorda?";
  - pergunta de duas partes;
  - pergunta que exige ler o post de novo para responder.
- **Fechar sem pergunta é permitido** quando a última frase é forte. Isso entra como variação em teste (§9). Nos dados, a pergunta final custa ~7% de reações e traz +0,5 comentário.
- **Hashtags:** 0 ou 1, na última linha. Específica (`#AgentesDeIA`), nunca genérica (`#Inovacao`).
- **Fonte:** continua na imagem (`voz.md` §7). Quando o número é forte, o texto diz de onde ele vem ("segundo a própria empresa").

## 7. O que soa como IA (lista de cortes)

O redator relê o texto contra esta lista antes de entregar. Duas ocorrências de qualquer item são reescritas.

**Estrutura:**
- todo post com o mesmo esqueleto (o problema do T2: hook, contexto, `•`, `→`, lição e pergunta, sempre);
- três itens em toda lista, três adjetivos em toda frase;
- toda lista com rótulo e dois-pontos em cada item;
- parágrafos todos do mesmo tamanho;
- frase de moral no fim ("Essa é a lição de negócio:", "Fica a reflexão", "O recado é claro");
- pergunta retórica seguida da resposta ("E o mais interessante? ...").

**Fórmulas:**
- "Não é X, é Y" e "não é sobre X, é sobre Y": no máximo uma por post;
- "Em um mundo onde...";
- "cada vez mais";
- "Vale ressaltar";
- "Na prática," abrindo parágrafo;
- "Spoiler:";
- "Resumindo:";
- "Vamos lá";
- "E aqui está o ponto".

**Palavras:**
- mergulhar;
- jornada (fora de "jornada do cliente");
- navegar;
- potencializar;
- alavancar;
- robusto;
- crucial;
- fundamental;
- ecossistema (fora do sentido técnico);
- transformador;
- "sem precedentes";
- e mais as palavras que o `voz.md` §8 já proíbe.

**Sinais:**
- seta `→` em todo post;
- travessão em toda frase;
- negrito simulado com caixa alta;
- emoji.

## 8. Marcação de cada post (para medir)

Todo post publicado leva, no registro da fila:

| Campo | Valores |
|---|---|
| `padrao` | P1 a P6, ou o ID de um padrão em teste |
| `estrutura` | E1 a E5 |
| `hook_tipo` | H1 a H6, mais o texto dos 3 hooks propostos e qual foi escolhido |
| `publico` | gestor, builder, estudante |
| `opiniao_felipe` | sim ou não (e se foi escrita por ele ou escolhida entre as duas propostas) |
| `fechamento` | escolha, público nomeado, experiência, sem pergunta |
| `imagem` | layout ou fotos, e se tem número grande |
| `horario` | dia da semana e hora |
| `variacao` | o que está em teste neste post (§9), ou nada |

O coletor de métricas (ADR 0009) junta as leituras ao post pelo URN.

## 9. Como o playbook aprende

**O placar.** Cada post é comparado com a **mediana móvel dos últimos 10 posts do linky na mesma idade**, nunca com números absolutos: a rede de Felipe muda, e a mediana muda junto.

| Critério | Medida | Leituras |
|---|---|---|
| Alcance | impressões ÷ mediana | aos ~24h e aos ~7 dias |
| Conversa | comentários (inclui as respostas de Felipe, o que fica declarado no relatório) | aos 7 dias |
| Seguidores e perfil | seguidores ganhos + visitas ao perfil vindas do post | aos 7 dias |
| Oportunidades | contatos, propostas e convites que Felipe atribui ao post | uma pergunta no relatório mensal |

**Exploração.** Cerca de 1 post em cada 4 leva uma variação em teste: um padrão novo das referências, um hook menos usado, ou o fechamento sem pergunta. **Uma variação por post**, para saber o que mexeu no número.

**O que o sistema pode mudar sozinho:**
- a ordem de preferência dos hooks, das estruturas e dos padrões de pauta;
- os exemplos deste playbook, trocados por posts de Felipe que foram bem;
- a entrada de um padrão novo como "em teste", e a promoção dele a ativo;
- o acréscimo de itens à lista de cortes (§7).

**Quando pode mudar:**
- **promover** um tipo (hook, estrutura, padrão ou fechamento): pelo menos 6 posts dele, com razão mediana de 1,3x ou mais no alcance **e** sem piora na conversa;
- **rebaixar** um tipo para "em pausa": pelo menos 6 posts, com 0,7x ou menos no alcance **e** na conversa.

No máximo **2 mudanças por semana**, cada uma registrada na §11 com os números.

**O que o sistema não pode mudar:**
- o `voz.md`;
- as regras de fato e de primeira pessoa;
- a regra de um post por dia;
- o tamanho máximo;
- os itens proibidos das §3 e §6;
- tirar itens da lista de cortes.

Mudanças desse tipo viram **proposta** no relatório mensal, e só Felipe aprova.

**Relatório mensal** (por e-mail, a partir do fim da semana 4):
- o placar do mês;
- os 3 melhores e os 3 piores posts, com a leitura do porquê;
- as mudanças feitas e as propostas;
- uma pergunta sobre oportunidades.

## 10. Calendário

| | Regra |
|---|---|
| Dias | **Segunda a sexta**, 1 post por dia. Nada no fim de semana |
| Horário | **18:30**, o mesmo do T2, nas 4 primeiras semanas. Formato, hook e frequência já mudam ao mesmo tempo; mudar o horário também deixaria os números ilegíveis. Depois, testar 09:00 como variação (exige pauta e aprovação na véspera) |
| Mix da semana | 3 a 4 análises (E1 a E3) e 1 a 2 posts de Felipe (E4 ou E5, por pedido, ADR 0008). Sem pedido de Felipe na semana, as 5 vagas são de análise |
| Nunca dois no mesmo dia | Um post pessoal que Felipe publica por conta própria conta como o post do dia: avisar o sistema (pedido ou e-mail) para liberar o horário |
| Diversidade | Nunca duas vezes seguidas a mesma empresa; no máximo 2 posts do mesmo tema em 5 seguidos (rubrica v1, pergunta 3) |
| Pautas | Iguais a hoje: seg a sex às 07:00 (3 cards) e domingo às 21:00 (5 cards, para a segunda e o banco). **Novo no e-mail de domingo:** "Tem algo da sua semana que vira post?", com o link do pedido (ADR 0008) |

O calendário mudou (16/11) nestes lugares:
- `config/editorial.yaml`: `slots.weekdays: [mon, tue, wed, thu, fri]`, que só vale depois do deploy do serviço;
- o gatilho do `linkyPublish`: `30 18 * * 1-5` em `n8n/linky-publicacao.json`, reimportado;
- o PRD (§7.6 e a tabela de regras);
- `README.md`, `ops/README.md`, `CONTINUIDADE.md` e a docstring de `linky_agents.editorial`.

## 11. Registro de mudanças

| Data | Mudança | Por quê | Quem |
|---|---|---|---|
| 16/11/2026 | v2: padrões, 6 hooks, 5 estruturas, fechamento novo, lista de cortes, marcação, regras de aprendizado, calendário de 5 posts | Laboratório editorial (13/11) | Claude; aprovado por Felipe em 16/11 |

## Apêndice: o post da Uber no formato E1 (comparação)

**Como saiu no T2 (12/11, 23 impressões):** o esqueleto completo, com 3 itens `•`, 3 itens `→`, "Essa é a lição de negócio", pergunta aberta e 3 hashtags (`eval/gold/2026-11-09.json`).

**Como ficaria agora,** com os mesmos fatos. A "Minha leitura" está em voz neutra, porque não houve opinião de Felipe nesse post:

```
Agentes de IA de outras empresas pediram 4 corridas na @Uber. Quatro.

O número saiu na apresentação de resultados do 3º trimestre. No Uber Eats, foram cerca de 500 pedidos na semana do Halloween, uma das mais movimentadas do ano.

O CEO, que já comandou a Expedia, disse por que não quer um intermediário: lá, dependia "dos Googles do mundo", e não quer voltar a isso. No Brasil, a dona da 99 disse ao Tecnoblog que o volume pedido por agentes é insignificante.

O ponto que importa: antes de preparar a empresa para ser comprada por agentes, vale perguntar se o seu cliente já quer delegar a compra. Por enquanto, os dados dizem que não.

Uma ressalva: são números da própria Uber, que tem todo o interesse em mostrar que o app continua sendo a porta de entrada.

Você deixaria um agente pedir seu almoço hoje? Sim ou ainda não?

#AgentesDeIA
```

A menção aparece aqui como `@Uber`; no post vai no formato little, `@[Uber](urn:li:organization:1815218)`. São cerca de 780 caracteres. O que mudou:
- o hook passou a ser H2 (número seco) com a virada na mesma linha;
- a lista virou prosa;
- entrou a ressalva honesta;
- a pergunta é de escolha;
- ficou uma hashtag;
- não tem frase de moral.
