# PRD: linky-dev, esteira agêntica de conteúdo para o LinkedIn

> **Versão:** 1.3 · **Data:** 2026-11-11 · **Base:** briefing de descoberta, rev. 3
> **Mudanças da v1.3:** **post sob demanda** por e-mail, com notícia, tema livre ou experiência, remarcação de horário e pedido urgente (§7.8, [ADR 0008](adr/0008-post-sob-demanda.md)).
> **Mudanças da v1.2:** **fila editorial** com horários fixos (seg, qua e sex, 18:30), validade de pauta e regras para e-mail não respondido (§7.6, [ADR 0001](adr/0001-fila-editorial.md)); **direção de arte com liberdade criativa** dentro da identidade visual, no lugar de 3 moldes fixos (§7.7, [ADR 0002](adr/0002-direcao-de-arte.md)); o agendamento da publicação entra no MVP.
> **Mudanças da v1.1:** teto de custo de **US$ 3/mês**; os créditos existentes deixam de contar como orçamento; repositório privado; D17 decidida (harness próprio em Python); posição sobre D9; lista de fontes e identidade visual viram trabalhos paralelos.
> Itens marcados com **[H]** são hipóteses ainda não provadas (ver 7.5).

## 1. Resumo

O linky-dev é um sistema de agentes que, todos os dias, pesquisa notícias de IA e de IA para negócios, propõe 3 pautas e, depois da escolha de Felipe Lenzi, produz legenda e imagem para o LinkedIn dele. Nada é publicado sem a aprovação final de Felipe.

O sistema roda com **no máximo US$ 3 por mês** em modelos de IA. Usa modelos baratos por padrão e reserva um modelo mais capaz só para a etapa que comprovadamente precisar dele.

O projeto tem dois objetivos: aumentar a visibilidade profissional de Felipe e, depois de validado em produção, virar um case público no GitHub.

## 2. Contatos

| Nome | Papel | Comentário |
|---|---|---|
| Felipe Lenzi | Dono do produto, autor e único usuário | Toma as duas decisões: escolhe a pauta e aprova o post |

## 3. Contexto

Postar com consistência sobre IA exige pesquisar, filtrar, escrever e criar arte. Felipe quer manter essa presença sem gastar horas por post. Também quer provar, com um sistema real, que constrói agentes com qualidade, custo baixo e humanos no ponto certo.

**Por que agora:**
- Modelos pequenos (GPT-5-nano, DeepSeek Flash, Haiku 5.5) custam centavos por milhão de tokens. Isso permite uma esteira diária por bem menos de US$ 3 por mês, se o sistema for desenhado para economizar tokens.
- A API oficial do LinkedIn permite publicar com imagem no perfil pessoal.
- O n8n de Felipe (`n8n.example.com`) acabou de ser limpo e atualizado. Tem cerca de 950 MB de RAM livre e backup diário.

## 4. Objetivo

**Objetivo:** publicar com regularidade conteúdo de IA na voz de Felipe, com poucos minutos de atenção humana por post e custo de IA mínimo, e documentar o sistema como case.

**Resultados-chave (nas 6 primeiras semanas de MVP):**
1. **Tempo:** no máximo **15 minutos** de atenção humana por post, somando as duas decisões. **Linha de base (T1, medida por Felipe):** de 40 minutos, quando a notícia já estava escolhida, a mais de 1 hora, com a pesquisa incluída e o trabalho quebrado ao longo do dia. A meta representa uma redução de ~60–80%. **[H]**
2. **Qualidade:** em pelo menos **80%** dos dias há uma pauta aproveitável, e pelo menos **60%** dos posts são aprovados com no máximo uma edição leve. **[H]**
3. **Regularidade e custo:** pelo menos **15 posts** publicados, com custo de IA **sempre abaixo de US$ 3/mês** (meta operacional: no máximo US$ 1,50) e menos de 10% de execuções com falha.

A visibilidade (impressões, reações e seguidores) é acompanhada por post, mas não vira meta no MVP. Em seis semanas, o algoritmo varia demais para esse número ser confiável.

## 5. Segmentos

1. **O autor-especialista sem tempo (principal):** Felipe, profissional de IA que precisa de presença autoral no LinkedIn, mas não tem horas diárias para produzir. As restrições:
   - O sistema publica em seu nome, então qualquer erro afeta a reputação dele.
   - O custo de IA tem teto rígido de US$ 3/mês.
   - Modelos caros devem ser evitados.
   - A VPS tem 2 GB de RAM e é compartilhada com fluxos de venda de outro projeto.
   - A identidade visual da marca ainda não existe.
2. **Quem avalia o portfólio (secundário, depois da publicação):** recrutadores, pares técnicos e possíveis clientes que querem ver se Felipe constrói agentes confiáveis. A restrição: só verão o repositório depois que o sistema estiver validado e as partes publicáveis tiverem sido escolhidas.

## 6. Propostas de valor

**Segmento 1, o autor-especialista**
- **Quem:** Felipe, autor de conteúdo de IA no LinkedIn.
- **Por quê:** manter uma presença constante e autoral. O que atrapalha é o tempo gasto em pesquisa, escrita e arte.
- **O que acontece antes:** pesquisa manual, texto do zero, arte quando dá. Resultado: posts irregulares.
- **Como:** agentes baratos e bem ajustados fazem a curadoria e o rascunho. Felipe só escolhe a pauta e aprova o post, nos dois casos por e-mail com formulário.
- **O que muda depois:** cerca de 3 posts por semana na voz dele, com cerca de 15 minutos de atenção cada e menos de US$ 3 por mês. Ele passa de produtor a editor-chefe.
- **Alternativas:** geradores de post genéricos ou ChatGPT e Claude usados à mão. Ele escolheria o linky-dev porque a curadoria é do nicho dele, nada sai sem aprovação, o custo é quase zero e é controlado, e os dados ficam com ele.

> **Proposta:** para um especialista em IA sem tempo, o linky-dev transforma o noticiário do dia em posts prontos na voz dele, por centavos, e ele só decide o que entra e o que sai.

**Segmento 2, quem avalia o portfólio**
- **Quem:** recrutadores, pares técnicos e clientes.
- **Por quê:** julgar se Felipe entrega agentes de verdade. O que atrapalha é que portfólios costumam mostrar demos sem uso real.
- **O que acontece antes:** READMEs bonitos, sem evidência de qualidade, custo ou operação.
- **Como:**
  - um harness com contratos tipados;
  - avaliações automáticas que barram regressões;
  - custo medido por chamada;
  - decisões documentadas;
  - humanos nas duas decisões críticas.
- **O que muda depois:** conseguem avaliar a competência em minutos, com números como custo por post e qualidade por modelo.
- **Alternativas:** projetos de tutorial. Escolheriam este porque roda em produção, publica de verdade e mostra os números.

> **Proposta:** um case de agentes em produção, com qualidade medida e custo de centavos por post, verificável por qualquer pessoa.

## 7. Solução

### 7.1 Fluxo principal

1. **Coleta contínua:** o coletor roda a cada 3 horas, por código, sem IA (fontes fixas, dedupe e filtros simples antes de gastar qualquer token).
2. **Pautas (decisão 1):** o harness roda a **triagem** e a **curadoria** e envia um e-mail com cards:
   - **seg a sex, 07:00:** 3 cards, com o que saiu desde o e-mail anterior;
   - **sábado:** nada;
   - **domingo, 21:00:** 5 cards, cobrindo sexta, sábado e domingo.

   Cada card traz o que aconteceu, por que importa, a abordagem sugerida, as fontes e a **validade**. O e-mail também mostra a **agenda** (próximos horários e o que já está marcado) e repete até 3 pautas de dias anteriores ainda válidas.
3. Felipe marca **de 0 a 3 pautas** (de 0 a 5 no domingo) e escolhe para cada uma: **produzir para o próximo horário livre**, **produzir para uma data** ou **guardar no banco**. Pode escrever a opinião em uma linha. A pauta escolhida **reserva** o horário na fila (§7.6).
4. O harness **redige** a legenda, **checa os fatos** contra as fontes e faz a **direção de arte** (§7.7). O motor transforma a composição em PNG.
5. **Decisão 2:** um e-mail com a legenda, a imagem e o horário reservado oferece **Aprovar** (podendo trocar o horário), **Pedir ajuste** (até 3 rodadas) ou **Descartar**.
6. **Publicação:** nos horários fixos (**seg a sex, 18:30**, desde 16/11/2026; antes seg, qua e sex), o n8n publica o post aprovado daquele horário por código determinístico, registra a URL e envia a confirmação. Sem post aprovado, o horário fica vazio. **Nunca se publica sem aprovação.**

### 7.2 Funcionalidades obrigatórias do MVP

- **Coleta determinística** a partir de `sources.yaml`, com dedupe por URL e por título, filtro de palavras-chave e limite de itens por fonte. Os agentes **não navegam na web**: recebem só o texto coletado. Isso corta custo e reduz o risco de *prompt injection*.
- **Curadoria com rubrica explícita:** novidade, relevância para negócios, evidência, ângulo Brasil e aderência ao posicionamento de Felipe. Os links das fontes vão em cada card.
- **Duas decisões por e-mail**, sempre por formulário com botão de envio. Nunca por link de clique único, porque scanners de e-mail abrem links sozinhos.
- **Redação na voz de Felipe**, a partir de `voz.md` e de 5 a 10 posts antigos dele como exemplo.
- **Checagem de fatos** por um modelo de outro fornecedor que não o do redator.
- **Imagem única com direção de arte livre dentro da identidade visual** (§7.7): o agente escolhe a metáfora visual da notícia e compõe com uma biblioteca de componentes. O motor (SVG → PNG) garante tokens, fontes, margens e a regra da retícula.
- **Fila editorial** (§7.6): horários fixos, reserva de horário, validade das pautas, banco de pautas, prazos de aprovação, adiamento, antecipação e modo silencioso.
- **Publicação segura:** só depois da aprovação, e a credencial do LinkedIn fica só no nó de publicação do n8n.
- **Governança de custo** (ver 7.4): registro por chamada, tetos por execução, por dia e por mês, e limites de gasto configurados também nos consoles dos fornecedores.
- **Registro completo** de pautas, escolhas, edições, custos e publicações, versionado no repositório privado.

### 7.3 Arquitetura (D17 decidida)

**Decisão: o n8n orquestra e um harness próprio em Python executa os agentes.**

| Componente | Responsabilidade |
|---|---|
| **n8n** (já existe) | Agenda, coleta HTTP e RSS, e-mails com formulário, espera pelas decisões, publicação no LinkedIn e alertas. É onde o n8n é forte: integrações e humano no meio do fluxo |
| **Harness `linky-agents`** (novo) | Agentes, prompts versionados, roteamento de modelos, validação de saídas, registro de custo, renderização da imagem e avaliações. Roda num container Docker com limite de 256 MB de RAM, **sem rota pública**: só o n8n o acessa, pela rede interna |

**Por que o harness e não nós de IA do n8n (raciocínio de dev sênior e gestor):**
- **Qualidade exige teste.** Você pediu parâmetros ajustados com rigor. Isso só se prova com avaliação automática a cada mudança de prompt ou de modelo. Em nós do n8n, prompts ficam presos em JSON de workflow, sem teste unitário, sem diff legível e sem barreira de regressão.
- **Custo exige controle fino:** contar tokens antes da chamada, cortar contexto, ordenar o prompt para aproveitar cache, ler o uso real da resposta e parar quando o teto estoura. Os nós prontos expõem só parte desses parâmetros. Há relatos de atrito com o modo de raciocínio da DeepSeek em nós de agente do n8n.
- **Troca de fornecedor sem reescrever fluxo.** O roteamento fica num arquivo de configuração, e o n8n não muda quando um modelo muda.
- **Cabe na VPS.** Com cerca de 950 MB livres, um serviço Python pequeno com teto de 256 MB não ameaça os fluxos de outro projeto.
- **O custo dessa escolha:** mais código para manter. A mitigação é manter o harness pequeno: só agentes, sem framework pesado, com uma camada fina de adaptação por fornecedor.

### 7.4 Harness de agentes: padrões de qualidade e parâmetros iniciais

**Padrões de engenharia (obrigatórios):**
1. **Contrato tipado por agente.** Entrada e saída têm esquema (Pydantic + JSON Schema). A saída é validada, e se vier inválida há 1 nova tentativa com o erro como contexto; depois disso, cai para o modelo reserva.
2. **Prompts versionados** em arquivos, com ID e versão gravados em cada execução. Parte fixa no começo e parte variável no fim, para maximizar o cache.
3. **Orçamento de tokens antes da chamada.** O harness estima a entrada, corta o contexto pelo limite do agente e define o máximo de saída. Nada vai sem limite.
4. **Ledger de custo** com o uso real devolvido pela API multiplicado por uma tabela de preços versionada, mais teto por execução, por dia e por mês, com corte automático e e-mail de alerta. Os consoles dos fornecedores também ficam com limite.
5. **Timeouts, até 2 tentativas com espera crescente e cadeia de fallback** por agente, com toda troca registrada.
6. **Avaliações como barreira.** Um *gold set* nasce na Fase 0. Qualquer mudança de prompt, modelo ou parâmetro só entra se a nota não cair (CI no GitHub Actions do repositório privado).
7. **Segurança:** o texto vindo da web é tratado como dado não confiável e vai delimitado. Agentes não têm ferramentas nem credenciais. Logs não guardam segredos.
8. **Rastreabilidade:** cada execução gera um registro JSON com entradas, versões, modelos, tokens, custo, latência e saída.

**Parâmetros iniciais por agente.** São pontos de partida. O ajuste final sai das avaliações (T7), não de achismo. Preços por milhão de tokens consultados em 05/11/2026.

| Agente | Modelo inicial → reserva | Raciocínio | Entrada / saída máx. | Execuções/mês | Custo/mês estimado |
|---|---|---|---|---|---|
| Triagem (relevância, categoria, resumo de 1 linha) | GPT-5-nano → DeepSeek Flash | mínimo ou desligado | 10k / 1,5k | 30 | ~US$ 0,03 |
| Curadoria (ranking + 3 cards) | GPT-5-mini → DeepSeek V4 Pro (fora do pico) | baixo | 15k / 3k | 30 | ~US$ 0,30–0,50 |
| Redação (legenda na voz de Felipe) | DeepSeek V4 Pro → Sonnet 5.5, só se o T7 provar que precisa | baixo / desligado | 8k / 3k | ~20 | ~US$ 0,25 (Sonnet com cache: ~US$ 0,40) |
| Checagem de fatos | GPT-5-mini (outro fornecedor que o redator) | baixo | 8k / 1,5k | ~13 | ~US$ 0,07 |
| Direção de arte (JSON do template) | GPT-5-nano | mínimo | 2k / 0,4k | ~13 | < US$ 0,01 |
| **Total operacional** | | | | | **~US$ 0,65–1,00/mês** |

*Premissas:* curadoria diária; cerca de 13 posts por mês; 1,5 redação por post (ajustes); coleta cortada a cerca de 40 itens por dia antes da triagem; textos de artigo truncados em cerca de 1.200 tokens. Os tokens de raciocínio contam como saída, e por isso as saídas máximas incluem margem.

- **Folga até o teto:** a comparação de modelos (T7) e eventuais reprocessamentos usam a folga até US$ 3, limitada a US$ 1 por mês.
- **Parâmetros específicos de cada API** (temperatura, níveis de raciocínio aceitos, cache): mudam por modelo e serão fixados no código depois da verificação na documentação de cada fornecedor.
- **Atualização de 10/11/2026 (etapa G, [g-pesquisas §3](discovery/g-pesquisas.md)):** a OpenAI desliga o GPT-5-nano e o GPT-5-mini em 11/12/2026. Em `config/models.yaml` (v2), triagem, curadoria, checagem e arte passam a começar no **GPT-6 Luna** (US$ 0,10/0,50); o T7 decide se curadoria e checagem precisam do GPT-5.4-mini. O DeepSeek Flash agora se chama `deepseek-flash`. Raciocínio explícito em todos os modelos. Custo estimado: ~US$ 0,40–0,60/mês.

### 7.5 Hipóteses e perguntas em aberto

**Hipóteses a validar**
- **[H]** O app do LinkedIn com `w_member_social` publica imagem pelo `/rest/posts` como pessoa, talvez exigindo uma Página vinculada → T3.
- **[H]** Modelos pequenos fazem triagem e curadoria sem perder as pautas que Felipe escolheria, e um modelo intermediário escreve na voz dele com edição leve → T2 + T7.
- **[H]** O custo real fica abaixo de US$ 1,50/mês → registro das primeiras 2 semanas.
- **[H]** n8n + harness rodam estáveis em 2 GB ao lado de outro projeto → T8.
- **[H]** Scanners de e-mail não disparam os formulários → T4′.

**D9, transparência (decidida em 10/11/2026: sem rótulo por post, transparência no perfil e nos bastidores; G1 em [g-pesquisas](discovery/g-pesquisas.md)):**
- **Verificado em 10/11/2026 ([g-pesquisas §1](discovery/g-pesquisas.md)):** o LinkedIn não exige rótulo de IA em texto de perfil pessoal, nem pela API; só recomenda avisar quando o autor “dependeu muito” de IA, e reduz o alcance de conteúdo genérico (“AI slop”). O selo C2PA vale só para imagem e vídeo assinados, e nossas imagens não são geradas por IA. Os Termos da API proíbem publicação automatizada sem participação do membro: a aprovação do conteúdo exato, com opção de ajuste, é o que nos deixa do lado certo.
- **Não marcar cada post como “feito por IA”.** O post é seu de fato: você escolhe a pauta, dá a opinião, edita e aprova.
- **Ser transparente sobre o processo.** Diga no perfil (seção Sobre ou Destaques) que você usa um sistema próprio de curadoria com IA. E transforme a construção do linky-dev numa **série de posts**: como funciona, quanto custa, o que deu errado. Para quem acompanha IA, isso tende a engajar mais que notícia, porque é experiência própria e difícil de copiar **[H]**. Também prepara o lançamento público do repositório.
- **Regra inegociável:** o sistema nunca inventa experiências pessoais suas. A opinião em primeira pessoa vem da sua linha na decisão 1.
- **Teste:** comparar o engajamento dos posts de bastidores com o dos posts de notícia nas primeiras semanas.

**Perguntas em aberto e trabalhos paralelos**
- **D10, lista de fontes:** ainda não existe e vai ser montada na Fase 0, com critérios: fonte primária, RSS disponível, sinal/ruído, frequência, ausência de paywall e fontes brasileiras. A validação é rodar a coleta por 7 dias e podar as fontes que não geram pautas escolhidas.
- **D12, identidade visual:** passa a ser criada **neste projeto, com o Claude**, na Fase 0, a partir do posicionamento definido no guia de voz. A entrega é um JSON de tokens (cores, tipografia, espaçamentos, logo) mais templates SVG. Até lá, vale o template neutro.
- **Voz:** os posts antigos de Felipe foram gerados com IA e não definem uma voz própria. O guia de voz será **construído do zero** num workshop na Fase 0, antes da semana Mágico de Oz.
- **D18 e D19, fornecedores e dados (decididas em 10/11/2026 como sugerido: OpenRouter só nas avaliações; DeepSeek só com dados públicos e fora da redação pela API oficial; G3 e G5 em [g-pesquisas](discovery/g-pesquisas.md)):** usar OpenRouter só nas avaliações? A DeepSeek fica restrita a etapas com dados públicos? A sugestão é sim para as duas. `voz.md` e as suas opiniões vão só para fornecedores que você aprovar.
  - **Pesquisado em 10/11/2026 ([g-pesquisas §2 e §5](discovery/g-pesquisas.md)):** a DeepSeek guarda os dados na China, sob lei chinesa, enquanto a conta existir, e não exclui o treino com dados da API (opt-out só por e-mail). OpenAI e Anthropic não treinam com dados da API e apagam em até 30 dias. Recomendação: DeepSeek só como reserva da triagem e da curadoria; na redação (que leva `voz.md` e a sua opinião), trocar de fornecedor ou usar o V4 Pro servido nos EUA via OpenRouter, decidido no T7. OpenRouter: opcional no T7 (5,5% sobre créditos, sem markup), com `data_collection: deny`; produção direta nos fornecedores. **Falta o seu OK.**
- **Política do LinkedIn sobre conteúdo com IA:** ✅ verificada em 10/11/2026: não há regra de rotulagem para texto (ver D9 acima e [g-pesquisas §1](discovery/g-pesquisas.md)).
- **Logos de empresas:** Microsoft, NVIDIA e Google exigem licença para o logo; o nome escrito é livre quando a informação é verdadeira. Padrão: nome escrito; logo só com permissão editorial registrada em `assets/logos/fontes.yaml` ([g-pesquisas §4](discovery/g-pesquisas.md)).

### 7.6 Fila editorial (v1.2, [ADR 0001](adr/0001-fila-editorial.md))

**Princípio:** gostar de uma pauta e decidir quando ela sai são decisões separadas. A pauta escolhida reserva um horário, e a fila garante que dois posts nunca disputem o mesmo dia.

| Regra | Valor (em `config/editorial.yaml`) |
|---|---|
| Horários de publicação | Seg a sex, 18:30 (5 por semana desde 16/11/2026, `playbook.md` §10). No máximo 1 por dia. Fora desses dias, nada é publicado |
| E-mail de pautas | Seg a sex às 07:00 (3 cards). Sábado, nada. Domingo às 21:00 (5 cards, de sexta a domingo) |
| Validade | Perecível (notícia quente): até 4 dias após o fato. Duradoura (caso, pesquisa, tese): até 14 dias. O curador classifica cada pauta |
| Prazo de aprovação | Até 16:30 do dia do horário. Lembrete às 12:00 se ainda não estiver aprovado |
| Revalidação | Post aprovado há mais de 48 horas é conferido de novo antes de sair: a notícia mudou? Alguma referência de tempo, como "na última terça", ficou errada? Mudança relevante volta para Felipe |
| Publicação falhou | Não reenvia sozinha, para evitar post duplicado. Felipe recebe alerta |

**Quando Felipe não vê o e-mail:**
1. **As pautas não somem com o e-mail.** Cada card vale até a data de validade. O formulário de um e-mail antigo continua funcionando enquanto a pauta valer; depois, mostra "venceu".
2. **Repescagem:** o e-mail seguinte repete até 3 pautas ainda válidas e sem resposta, começando pelas que vencem primeiro.
3. **Post sem aprovação no prazo:** não é publicado. Vai para o próximo horário livre, se a pauta ainda valer, ou vence. Felipe é avisado.
4. **Horário vazio:** um post já aprovado e marcado como "próximo horário livre" é **antecipado** automaticamente. Post com data escolhida por Felipe nunca é movido.
5. **Modo silencioso:** depois de 3 e-mails de pauta seguidos sem nenhuma resposta, os e-mails diários param e só o de domingo continua, com um resumo. Qualquer resposta reativa tudo. Isso evita lotar a caixa de entrada e gastar tokens à toa.

**Implementação:** `src/linky_agents/editorial.py` (estados, calendário e regras, com 19 testes), persistido em SQLite no harness. O n8n só aciona: um relógio de hora em hora chama `tick` (adiar, vencer, lembrar, antecipar, revalidar), e cada horário de publicação chama `due`.

### 7.7 Direção de arte (v1.2, [ADR 0002](adr/0002-direcao-de-arte.md))

Os 3 layouts da v1 (escada, contraste e tese) deixam de ser moldes e viram **exemplos** de uma linguagem visual.
- O agente de direção de arte escolhe a **metáfora visual** de cada notícia e compõe a imagem com uma **biblioteca de componentes** sobre a grade da marca: manchete com destaque, número em destaque, pilhas de comparação, linha do tempo, antes e depois, funil, matriz 2×2, checklist, escada, equação, citação e fluxo.
- O motor garante a identidade: só tokens e fontes da marca, margens, contraste, lima apenas em detalhes e a regra da retícula. Uma composição inválida é recusada com o motivo, e o agente corrige.
- **Válvula criativa:** quando nenhum componente serve, o agente pode desenhar um diagrama próprio dentro de uma área delimitada. Nesse caso, e só nele, um modelo com visão revisa o resultado.
- **Anti-repetição:** a mesma composição não se repete num intervalo de 5 posts.
- **Como a biblioteca nasce:** no T2, Claude faz a direção de arte livre à mão, post a post (`tools/t2_art/`). As peças que se repetirem viram os componentes da Fase 1.

### 7.8 Post sob demanda (v1.3, [ADR 0008](adr/0008-post-sob-demanda.md))

**Princípio:** além das pautas da curadoria, Felipe pode **pedir um post** por e-mail, sem interface nova. O pedido entra na fila como um post normal (já escolhido) e passa pela mesma redação, aprovação e publicação, com o mesmo teto de custo.

| Regra | Valor |
|---|---|
| Canal | E-mail para `pedido@in.example.com` (Resend Inbound). Só de `voce@example.com` com DKIM e DMARC válidos; outro remetente é ignorado em silêncio |
| Tipos | **Notícia** (com link ou só descrita; a notícia de verdade precisa ser achada, e a fonte vale mais que a descrição) · **tema livre** · **experiência** (só o que Felipe escreveu é fato; formato de relato, `voz.md` §6.1). Classificação automática |
| Fatos | Notícia e tema: base coletada, depois até 3 buscas na web; todo fato com fonte lida. Sem evidência, não escreve e responde. Experiência sem detalhe: pergunta o que falta |
| Imagem | Sem anexo: motor de composição. Com anexo: as imagens de Felipe, como vieram, até 9, texto alternativo por modelo com visão |
| Horário | Próximo horário livre. Data pedida: o pedido fica com ela e o post que estava lá é **remarcado** para o próximo horário livre depois dela (continua aprovado; perecível que vence volta para Felipe). Depois das 16:30 do dia: próximo horário livre |
| Urgente | "Tem que sair hoje": 18:30 em qualquer dia, aprovação até 18:15 (depois, ~15 min após aprovar), sem aprovação até 22:00 volta à regra normal. Máximo de 1 por dia salvo "além do de hoje". Nunca pula a aprovação |
| Conversa | Confirmação em ~1 min na mesma conversa (tipo, ângulo, horário, divergências, remarcações). Resposta na conversa = ajuste (nova versão). Aprovação só pelo formulário |
| Lançamento | Construído junto com o redator do MVP, depois da calibração do T2; primeiro em modo sombra |

## 8. Lançamento

| Fase | Duração relativa | Conteúdo |
|---|---|---|
| **0. Validar** | ~1–2 semanas | **T1:** medir o tempo atual por post. **T2:** semana Mágico de Oz (3 pautas por dia à mão, publicação manual), que gera o *gold set*. **T3:** criar o app do LinkedIn e fazer um post de teste. Montar a primeira versão de `sources.yaml` e coletar por 7 dias. Escrever `voz.md` e a rubrica. Criar o repositório privado e o esqueleto do harness |
| **1. MVP** | ~2–3 semanas | Fluxo completo da seção 7.1, com harness, fila editorial, ledger de custo, avaliações no CI e direção de arte por componentes. Depois, 6 semanas de uso medindo os resultados-chave |
| **2. Evoluir** | Depois do MVP | Comparação completa de modelos (T7) e ajuste fino; identidade visual definitiva; carrossel em PDF; série de bastidores no LinkedIn |
| **3. Publicar o case** | Depois de validado | Escolher o que vai a público (código, ADRs, métricas, avaliações) e o que fica privado (`voz.md` completo, gold set com dados pessoais, configurações). Revisão de segredos e lançamento com post próprio. **✅ 19/11/2026:** retrato público `LenziAI-DEV/linky` ([ADR 0010](adr/0010-repositorio-publico.md)); por decisão de Felipe, `voz.md` e gold set publicados completos; coletor de métricas, runbooks e briefing só no privado. Falta o post de lançamento |

**Fora do escopo do MVP:**
- carrossel ou várias imagens;
- Figma no caminho crítico;
- imagens geradas por IA;
- agentes navegando livremente na web;
- painel web próprio;
- leitura automática de métricas do LinkedIn;
- publicar em página de empresa ou em outras redes;
- usar modelos caros por padrão;
- qualquer publicação sem aprovação explícita.
