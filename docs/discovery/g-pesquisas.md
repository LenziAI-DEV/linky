# Etapa G: pesquisas antes de o MVP rodar sozinho (10/11/2026)

> **Escopo:** as cinco perguntas da linha G (CONTINUIDADE §4.6) e da §6. Todas as fontes foram consultadas em **10/11/2026**; as citações são trechos curtos das fontes primárias (documentação oficial, termos, central de ajuda, lei). Onde só havia fonte secundária, está dito.
> **Nenhuma chamada paga** às APIs de modelos foi feita. Os parâmetros abaixo vêm da documentação; a primeira chamada real de cada modelo (no T7) confirma.

## Resumo das decisões de Felipe

> **Decididas em 10/11/2026:** Felipe aceitou as cinco recomendações abaixo (G1 a G5), como estão.

| # | Decisão | Recomendação |
|---|---|---|
| G1 | **D9:** rotular os posts como feitos com IA? | Não rotular post a post; manter a transparência no perfil (seção Sobre) e na série de bastidores, como o PRD já propõe. Nada nas regras do LinkedIn exige rótulo para texto. Ver §1 |
| G2 | **Modelos OpenAI:** `gpt-5-nano` e `gpt-5-mini` saem da API em **11/12/2026**, no meio das 6 semanas de MVP | Trocar já para o `gpt-6-luna` (mais novo e mais barato que o substituto oficial) em triagem, curadoria, checagem e arte, e deixar o T7 decidir se a curadoria precisa de um modelo maior (`gpt-5.4-mini`). **Já aplicado em `config/models.yaml`**, reversível. Ver §3 |
| G3 | **D19:** onde a DeepSeek pode entrar | Só com dados públicos: triagem (reserva) e curadoria (reserva). **Tirar a DeepSeek da redação** (que leva `voz.md` e a opinião de Felipe) ou rodá-la por um host fora da China. Ver §2 |
| G4 | **Logos:** usar logos de empresas nas imagens? | Não por padrão: manter o nome escrito. Logo só de empresa cuja política permita uso editorial, registrada em `assets/logos/fontes.yaml`. Ver §4 |
| G5 | **D18:** OpenRouter só nas avaliações? | Sim, como opção para o T7 (5,5% de taxa sobre créditos, sem markup no token), com `data_collection: deny`. Produção continua direta nos fornecedores. Ver §5 |

---

## 1. LinkedIn e conteúdo feito com IA

**Resposta curta.** Não há exigência de rotular texto escrito com ajuda de IA em posts de perfil pessoal, nem pela interface nem pela API. O LinkedIn **recomenda** avisar quando a pessoa "dependeu muito" de IA e pune a distribuição de conteúdo genérico ("AI slop"), não o uso de IA. As credenciais de conteúdo (C2PA) valem só para imagem e vídeo assinados, e as imagens do linky-dev não são geradas por IA (o motor desenha SVG por código), então nada muda. O risco real está nos **Termos da API**, que proíbem usar as APIs "para automatizar a publicação"; o desenho do linky-dev (Felipe aprova cada post exato, com opção de editar, e o sistema só publica o que ele aprovou, no perfil dele) é o caso que a política de IA para desenvolvedores do próprio LinkedIn descreve como aceitável. **Conclusão para D9:** manter a recomendação do PRD (sem rótulo por post, transparência no perfil e nos bastidores), com duas regras novas: nada sai sem aprovação humana do conteúdo exato (já é regra) e a opinião em primeira pessoa é sempre de Felipe (já é regra).

**Evidências**

| Fonte | O que diz |
|---|---|
| [Central de Ajuda: boas práticas para conteúdo criado com ajuda de IA](https://www.linkedin.com/help/linkedin/answer/a1481496) (atualizada há ~2 semanas) | Recomenda, não exige: "we recommend that you let others know (if it isn't obvious from the context) if you've relied heavily on AI". Responsabilidade: "You are ultimately responsible for everything you post on LinkedIn". O conteúdo deve refletir a voz, a perspectiva e a experiência do membro; "AI slop" é conteúdo de baixo esforço sem ponto de vista |
| [Contrato do Usuário](https://www.linkedin.com/legal/user-agreement) (vigente desde 03/11/2025), §3.6 e §8.2 | Conteúdo gerado: revisar e editar antes de compartilhar, e o membro responde pelas Políticas da Comunidade. Nenhuma exigência de rótulo. §8.2 proíbe "bots or other **unauthorized** automated methods" (a API oficial é método autorizado) |
| [Central de Ajuda: credenciais de conteúdo](https://www.linkedin.com/help/linkedin/answer/a6282984) | O ícone C2PA aparece em "image and video content that is cryptographically signed using C2PA Content Credentials". Não cobre texto. Não há obrigação de assinar |
| [Termos de Uso da API](https://www.linkedin.com/legal/l/api-terms-of-use) (revisão de 13/12/2022, vigente desde 13/01/2023), §3.1 | Item 26: não "Use the Content or the APIs to automate posting on the LinkedIn Services". Item 1: nada que possa "harm the professional reputation" do membro. Item 3: não publicar "impersonating a Member". Nenhuma cláusula sobre IA ou rótulo |
| [Política de IA para desenvolvedores](https://learn.microsoft.com/en-us/linkedin/marketing/developer-ai-policy) (Marketing APIs, atualizada em 08/01/2026) | Formalmente vale para dados obtidos pelas Marketing APIs (não é o nosso caso, que usa o Share on LinkedIn), mas é o melhor indicador do que o LinkedIn espera: "Restrict automated posting of AI-generated content to external sites (including LinkedIn) ... without end user involvement" e, se o texto for atribuído ao usuário, dar ferramentas para "first edit the generated content" |
| [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin) | `w_member_social`: "Required to create a LinkedIn post on behalf of the authenticated member". Limite: 150 requisições por membro por dia |
| Cobertura de imprensa (secundária): [TechSpot](https://techspot.com/news/113580-people-have-clicked-like-ai-slop-button-linkedin.html), [Entrepreneur](https://www.entrepreneur.com/business-news/linkedin-is-fighting-back-against-ai-slop-and-ai-comments) | Botão "Seems like AI slop" desde 30/07/2026; classificadores reduzem o alcance de posts genéricos fora da rede imediata. Não achei o comunicado oficial |
| [AI Act da UE, art. 50(4)](https://artificialintelligenceact.eu/article/50/) (aplicável desde 02/08/2026) | Quem publica texto gerado por IA "to inform the public on matters of public interest" deve avisar, **exceto** quando o conteúdo "has undergone a process of human review or editorial control" e alguém "holds editorial responsibility". Felipe está no Brasil, mas, se valesse, a aprovação dele cobre a exceção |
| [Termos da Open Platform da DeepSeek](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) (vigentes desde 29/04/2026), §8.1 | Pede que o desenvolvedor avise os usuários finais de que as saídas são geradas por IA. Aqui o usuário final do app é o próprio Felipe, que sabe; o post publicado é texto dele, revisado e aprovado. Mais um motivo para manter a transparência no perfil |

**Como ler o item 26 dos Termos da API.** A frase é ampla e está numa lista sobre uso de "Content" do LinkedIn. O mesmo LinkedIn oferece o produto self-service "Share on LinkedIn" justamente para publicar "on behalf of the authenticated member", e as ferramentas de agendamento usam essa via. A leitura prudente: proibido é publicar sem a participação do membro (robô decidindo o que e quando sai). O linky-dev fica do lado certo se mantiver: (1) aprovação explícita do texto e da imagem exatos antes de cada post; (2) ajuste antes de aprovar; (3) nenhum reenvio automático; (4) no máximo 1 post por dia. As quatro já são regra (PRD §7.6). **Não é parecer jurídico**: se um dia o LinkedIn questionar, a defesa é o registro de aprovações da fila.

**Conclusão prática para o PRD D9:** sem rótulo por post (não é exigido e o post é de Felipe); transparência no perfil e na série de bastidores; nunca inventar experiência pessoal (já é regra); e cuidar da qualidade, porque o risco concreto em 2026 é alcance menor para texto com cara de IA genérica, não punição por uso de IA. Imagem: o motor não usa IA generativa, então não há C2PA a aplicar; se um dia entrarem imagens geradas por IA, preservar os metadados C2PA que o gerador anexar.

---

## 2. DeepSeek e a política de dados (D19)

**Resposta curta.** A DeepSeek guarda e processa os dados **na China**, sob lei chinesa, enquanto a conta existir; os termos da API **não** excluem o uso das entradas para treino, e o único opt-out é pedir por e-mail (`privacy@deepseek.com`), sem garantia documentada para a API. OpenAI e Anthropic, na API, **não treinam** com os dados por padrão e apagam em até 30 dias. **Recomendação:** a DeepSeek só recebe **dados públicos** (notícias coletadas, títulos, resumos): pode ficar como **reserva** da triagem e da curadoria. **`voz.md`, os exemplos de posts de Felipe e a opinião dele em uma linha não vão para a DeepSeek.** Isso afeta a redação, que hoje tem a DeepSeek V4 Pro como modelo inicial: Felipe escolhe entre (a) trocar a redação para outro fornecedor ou (b) manter o V4 Pro servido por um host fora da China via OpenRouter (§5).

**Evidências**

| Fonte | O que diz |
|---|---|
| [Política de Privacidade da DeepSeek](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html) (atualizada em 10/02/2026) | Dados são coletados, processados e guardados "in People's Republic of China". Retenção: enquanto a conta existir, e mais se houver obrigação legal. Entradas e saídas podem ser usadas "to train and improve our technology"; há direito de "opt-out of using your Personal Data for training", exercido por e-mail. Compartilhamento com governo para cumprir "government requests" |
| [Termos da Open Platform](https://cdn.deepseek.com/policies/en-US/deepseek-open-platform-terms-of-service.html) (publicados em 22/04/2026, vigentes desde 29/04/2026) | Lei da China continental (§10.1), foro em Hangzhou (§10.2). Não dizem se a DeepSeek usa entradas da API para treinar; nenhum opt-out próprio da API; remetem à política de privacidade para dados pessoais (§5.5) |
| [Uso de dados da API da OpenAI](https://developers.openai.com/api/docs/guides/your-data) | "data sent to the OpenAI API is not used to train or improve OpenAI models" (desde 01/03/2023); registros de abuso "retained for up to 30 days"; retenção zero só com aprovação |
| [Anthropic: dados e treino](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training) (atualizada em 18/08/2026) e [retenção](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data) (01/07/2026) | API: "By default, we will not use your inputs or outputs"; apaga "within 30 days"; até 2 anos se houver violação da política de uso |

**Comparação rápida**

| | DeepSeek | OpenAI (API) | Anthropic (API) |
|---|---|---|---|
| Treino com os dados | Possível; opt-out por e-mail | Não, salvo opt-in | Não, salvo feedback ou opt-in |
| Retenção | Enquanto a conta existir | Até 30 dias (abuso) | Até 30 dias |
| Jurisdição | China | EUA (residência opcional) | EUA |
| Retenção zero | Não oferece | Com aprovação | Por acordo |

**Por agente (recomendação)**

| Agente | Dados que leva | DeepSeek pode? |
|---|---|---|
| Triagem | Itens coletados (públicos) | Sim, como reserva |
| Curadoria | Itens + rubrica (pública no repositório quando ele abrir) | Sim, como reserva. A rubrica cita o posicionamento de Felipe, que já é público no perfil |
| Redação | `voz.md`, exemplos de posts, **opinião de Felipe** | **Não** pela API oficial. Opções em G3 |
| Checagem | Legenda (ainda não publicada) + fontes | Não (já não usa) |
| Arte | Manchete e números do post | Não (já não usa) |

**Decisão G3 (Felipe):** para a redação, recomendo **(b) no T7**: comparar o V4 Pro servido nos EUA (DeepInfra ou Azure, via OpenRouter com `data_collection: deny`) contra o Sonnet 5.5 e o `gpt-6-luna` no gold set, e decidir pela nota. Até lá, `config/models.yaml` mantém a cadeia atual da redação, porque **nenhum agente roda de verdade antes do T7** (os prompts finais dependem do T2). Se Felipe preferir não arriscar, a troca imediata mais simples é a redação começar no Sonnet 5.5 (custo maior, ~US$ 0,40/mês com cache, PRD §7.4).

---

## 3. Parâmetros do harness (CONTINUIDADE §4.3)

**Resposta curta.** Três problemas reais e várias correções finas, todas aplicadas em `config/models.yaml` (v2) e `config/prices.yaml` (versão `2026-11-10`), com 2 testes novos (181 passando):

1. **`gpt-5-nano` e `gpt-5-mini` saem da API em 11/12/2026.** O substituto oficial do mini (`gpt-5.6-terra`) custa 8× mais. Troquei os quatro usos pelo **`gpt-6-luna`** (US$ 0,10/0,50), mais novo (conhecimento até 18/05/2026) e de mesma faixa de preço. O T7 decide se curadoria e checagem precisam do `gpt-5.4-mini` (US$ 0,75/4,50, sem data de desligamento).
2. **`reasoning_effort: minimal` não existe no `gpt-6-luna`** (aceita `none`, `low`, `medium`, `high`, `xhigh`, `max`). Triagem e arte passam para `none`.
3. **Sem parâmetro de raciocínio, a DeepSeek pensa em `high`** e o Haiku 5.5 em `medium`, o Sonnet 5.5 em `high`: tokens de raciocínio contam como saída. Todos os modelos das cadeias agora têm o nível explícito.

Além disso: o Flash da DeepSeek mudou de nome (`deepseek-flash`; o antigo ainda é aceito), e entraram os preços de leitura de cache de todos os modelos (antes cobrados como entrada cheia).

### 3.1 IDs e parâmetros (conferidos em 10/11/2026)

| Modelo em `models.yaml` | ID na API | Raciocínio | Saída JSON | Fonte |
|---|---|---|---|---|
| `gpt-6-luna` | `gpt-6-luna` (snapshot único) | `reasoning_effort`: none, low, medium (padrão), high, xhigh, max | `response_format` aceita `json_object` ("An older method"; `json_schema` recomendado). O modelo lista structured outputs | [modelo](https://developers.openai.com/api/docs/models/gpt-6-luna), [Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |
| `gpt-5-nano` / `gpt-5-mini` (saem) | snapshots `2025-08-07`, **desligados em 11/12/2026** | — | — | [deprecações](https://developers.openai.com/api/docs/deprecations) (aviso de 11/06/2026) |
| `gpt-5.4-mini` (candidato do T7) | `gpt-5.4-mini-2026-03-17` | none (padrão), low, medium, high, xhigh | structured outputs | [modelo](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| `deepseek-flash` | `deepseek-flash` → DeepSeek-V4.1-Flash-1017. `deepseek-v4-flash` é nome antigo, ainda aceito e cobrado como Flash | `reasoning_effort`: `none` desliga; low, high (padrão), max. `minimal` vira low. `thinking: {type}` tem precedência | `json_object` (exige a palavra "json" no prompt; pode devolver conteúdo em branco, tratar como erro e tentar de novo) | [preços e modelos](https://api-docs.deepseek.com/quick_start/pricing), [chat completion](https://api-docs.deepseek.com/api/create-chat-completion), [JSON](https://api-docs.deepseek.com/guides/json_mode), [raciocínio](https://api-docs.deepseek.com/guides/thinking_mode) |
| `deepseek-v4-pro` | `deepseek-v4-pro` → DeepSeek-V4-Pro-0813 | igual ao Flash | igual ao Flash | idem |
| `claude-haiku-5-5` | `claude-haiku-5-5` | `output_config: {effort}`: low a max, **padrão medium**; `temperature` diferente do padrão dá 400 | Não há `response_format`. O harness não envia nada e lê o JSON do texto (funciona). Opção mais forte: `output_config.format` com JSON Schema | [preços](https://platform.claude.com/docs/en/about-claude/pricing) e skill `claude-api` (modelos de 03/11/2026) |
| `claude-sonnet-5-5` | `claude-sonnet-5-5` | `output_config: {effort}`, **padrão high**; `thinking: disabled` dá 400 | igual ao Haiku | idem |

**Achados que exigem cuidado no T7 (não mexi no código do harness, fora do escopo):**
- **DeepSeek em JSON:** a documentação não diz se `json_object` funciona em modo de raciocínio. A primeira chamada do T7 confirma. O conteúdo em branco já cai na regra do harness (saída inválida → nova tentativa → próximo modelo).
- **Escrita de cache na OpenAI:** a partir do GPT-5.6, a escrita de cache custa 1,25× a entrada, e o Chat Completions informa `prompt_tokens_details.cache_write_tokens`. O `OpenAICompatible` não lê esse campo, então o ledger cobra a escrita a 1×. Efeito desprezível (prompts curtos, US$ 0,025 por milhão de tokens escritos), mas vale ler o campo numa próxima mexida no harness.
- **Cache mínimo:** 1.024 tokens no GPT-5.6+ e 512 nos Claude 5.5. Partes fixas menores que isso não entram no cache.
- **Cabeçalho da Anthropic:** o harness envia `anthropic-version: 2023-06-01`, ainda aceito. A versão `2026-10-21` recusa `temperature`; não usamos.

### 3.2 Preços (US$ por milhão de tokens, consultados em 10/11/2026)

| Modelo | Entrada | Leitura de cache | Escrita de cache | Saída | Observação |
|---|---|---|---|---|---|
| `gpt-6-luna` | 0,10 | 0,01 | 0,125 | 0,50 | Flex/Batch: metade |
| `gpt-5.6-luna` | 0,20 | 0,02 | 0,25 | 1,20 | substituto oficial do nano |
| `gpt-5.4-mini` | 0,75 | 0,075 | — | 4,50 | |
| `gpt-5-nano` | 0,05 | 0,005 | — | 0,40 | sai em 11/12/2026 |
| `gpt-5-mini` | 0,25 | 0,025 | — | 2,00 | sai em 11/12/2026 |
| `deepseek-flash` (pico) | 0,30 | 0,006 | — | 1,20 | fora do pico: metade |
| `deepseek-v4-pro` (pico) | 1,32 | 0,044 | — | 3,96 | fora do pico: metade |
| `claude-haiku-5-5` | 0,10 | 0,01 | 0,125 | 0,50 | até 100 mil tokens de entrada |
| `claude-sonnet-5-5` | 2,00 | 0,10 | 2,50 | 10,00 | |

**Fora do pico da DeepSeek:** pico de 01:00 a 04:00 e de 06:00 a 10:00 UTC, de segunda a sexta; o resto (fins de semana e feriados chineses inclusive) custa **metade**, cache incluído. O harness já aplica; feriados chineses ele cobra como pico (superestima). As rotinas do linky-dev rodam de dia no Brasil (07:00 BRT = 10:00 UTC), ou seja, quase sempre fora do pico.

Fontes: [OpenAI](https://developers.openai.com/api/docs/pricing) e páginas de cada modelo, [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing), [Anthropic](https://platform.claude.com/docs/en/about-claude/pricing).

### 3.3 Custo estimado com a configuração nova

Com as premissas do PRD §7.4 (30 triagens e curadorias, ~20 redações, ~13 checagens e artes por mês, saída máxima sempre usada, sem cache):

| Agente | Modelo | US$/mês |
|---|---|---|
| Triagem | `gpt-6-luna` | ~0,05 |
| Curadoria | `gpt-6-luna` (low) | ~0,09 |
| Redação | DeepSeek V4 Pro (fora do pico) | ~0,22 (no pico: 0,45) |
| Checagem | `gpt-6-luna` (low) | ~0,02 |
| Arte | `gpt-6-luna` | < 0,01 |
| **Total** | | **~US$ 0,40–0,60** (antes: 0,65–1,00) |

Se o T7 pedir o `gpt-5.4-mini` na curadoria e na checagem: ~US$ 1,20/mês, ainda abaixo da meta de 1,50. Se a redação for para o Sonnet 5.5: a redação passa de ~0,22 para ~0,40 (com cache e saída menor que o máximo) a ~0,90 (pior caso, sem cache).

### 3.4 O que mudou nos arquivos

- `config/models.yaml` v2: `gpt-5-nano`/`gpt-5-mini` → `gpt-6-luna` (`none` em triagem e arte, `low` em curadoria e checagem); `deepseek-v4-flash` → `deepseek-flash` com `reasoning_effort: none`; `deepseek-v4-pro` com `low`; Haiku e Sonnet com `output_config: {effort: low}`. A redação mantém a cadeia (decisão G3).
- `config/prices.yaml` versão `2026-11-10`: preços de leitura de cache de todos os modelos, escrita de cache do `gpt-6-luna`, modelos novos (`gpt-6-luna`, `gpt-5.6-luna`, `deepseek-flash`); os antigos ficam para o histórico.
- `tests/test_harness_providers.py`: um teste garante que as cadeias não usam modelos desligados, que todo modelo tem preço de cache, que nenhum envia `temperature` e que o nível de raciocínio existe naquele fornecedor; outro confere o preço de cache da DeepSeek no pico e fora dele.

---

## 4. Logos de empresas

**Resposta curta.** As grandes empresas de IA e tecnologia **exigem licença para usar o logo** (o nome escrito é livre quando a informação é verdadeira). A lei brasileira protege a citação da marca em publicação "sem conotação comercial", mas o perfil de Felipe também promove a consultoria dele, então o argumento é mais fraco para o **logo** do que para o **nome**. **Recomendação:** manter o nome escrito na tipografia da marca linky como padrão (já é o que o motor faz) e só usar logo de empresa cuja política permita uso editorial, com o arquivo oficial e a fonte registrados.

**Evidências**

| Fonte | O que diz |
|---|---|
| [Lei 9.279/1996, art. 132, IV](https://www.planalto.gov.br/ccivil_03/leis/l9279.htm) | O titular não pode "impedir a citação da marca em discurso, obra científica ou literária ou qualquer outra publicação, desde que sem conotação comercial e sem prejuízo para seu caráter distintivo" |
| [Microsoft: uso de marcas](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general) | Logos "can never be used without an express license"; o nome pode ser usado "to truthfully convey information", inclusive em título de notícia |
| [NVIDIA: uso de logo](https://www.nvidia.com/en-us/about-nvidia/legal-info/logo-brand-usage/) | "may not be used in any manner that isn't expressly authorized in writing by NVIDIA" |
| [Google: termos de marca](https://partnermarketinghub.withgoogle.com/brands/google/trademarks-and-terms/terms-and-conditions/) | Uso de logo só se "Google expressly approves your permission request"; sem exceção editorial |
| OpenAI (`openai.com/brand`) | A página recusou a leitura automática (403). Conferir à mão antes de usar |
| Anthropic | O kit de mídia fica no newsroom (`anthropic.com/news`); não achei termos de uso publicados. Só fontes secundárias |

**Processo recomendado para `assets/logos/`**
1. **Padrão: nome escrito.** A manchete e os componentes usam o nome da empresa na tipografia linky. Nenhuma licença é necessária e a identidade visual fica consistente.
2. **Logo só com permissão clara de uso editorial.** Para cada empresa, uma linha em `assets/logos/fontes.yaml`: arquivo, URL oficial de onde veio (kit de imprensa ou página de marca), data, trecho da regra de uso e `permitido: sim|nao`. Sem linha com `sim`, o motor recusa o logo e usa o nome.
3. **Arquivo oficial, sem edição:** SVG do kit de imprensa, sem recolorir, distorcer ou recortar; nunca de agregadores (Wikimedia, Simple Icons, Brandfetch), que não dão licença de marca.
4. **Nunca sugerir parceria:** logo só ao lado da notícia sobre aquela empresa, nunca junto à marca de Felipe como se fosse cliente ou parceiro.
5. **Revisão humana:** a imagem com logo passa pela aprovação de Felipe como qualquer outra (já é regra).

Na prática, com Microsoft, NVIDIA e Google exigindo licença, o logo deve ser exceção. Isso combina com o guia visual (identidade forte e própria) e não custa nada.

---

## 5. OpenRouter só nas avaliações (D18)

**Resposta curta.** Vale como **opção** para o T7, não como requisito. Uma chave só dá acesso a dezenas de modelos (inclusive o DeepSeek V4 Pro servido nos EUA, o que ajuda a resolver D19), com preço de tabela do fornecedor e **5,5% de taxa** na compra de créditos. Com o teto do T7 em US$ 1/mês, a taxa fica em ~US$ 0,06. Produção continua direta nos fornecedores (menos um intermediário com os dados, cache e preço fora do pico da DeepSeek garantidos).

**Prós**
- Integra sem código novo: a API é compatível com a da OpenAI; basta um fornecedor `kind: openai` com `base_url: https://openrouter.ai/api/v1` em `models.yaml`.
- Compara modelos de fornecedores sem conta própria (Gemini, Qwen, Mistral etc.) e o DeepSeek V4 Pro em hosts fora da China: DeepInfra (US$ 1,30/2,60), Azure (US$ 1,91/3,83), DigitalOcean, entre outros.
- Privacidade controlável por requisição: `provider: {data_collection: "deny"}` ("use only providers which do not collect user data"), `zdr: true`, `only` + `allow_fallbacks: false` para fixar o host. O OpenRouter não registra prompts por padrão ("zero logging ... unless you opt-in").

**Contras**
- Mais um intermediário com os dados (empresa dos EUA).
- O mesmo modelo em outro host pode ter resultado e latência diferentes do fornecedor oficial (quantização, versão). O T7 precisa fixar o host para ser reprodutível.
- O preço fora do pico da DeepSeek e o cache dependem do host; o ledger precisaria de entradas por host em `prices.yaml`.
- Créditos pré-pagos: mais um saldo para acompanhar.

**Custo:** inferência ao preço de tabela ("no markup on inference pricing"), 5,5% sobre a compra de créditos; com chave própria do fornecedor (BYOK), sem taxa até US$ 25.000/mês.

Fontes: [preços do OpenRouter](https://openrouter.ai/pricing), [FAQ](https://openrouter.ai/docs/faq), [roteamento por fornecedor](https://openrouter.ai/docs/guides/routing/provider-selection), [DeepSeek V4 Pro no OpenRouter](https://openrouter.ai/deepseek/deepseek-v4-pro).

**Decisão G5 (Felipe):** criar a conta e comprar créditos é ato de identidade e pagamento, então fica com ele. Recomendo só se o T7 for testar o V4 Pro fora da China ou modelos de fornecedores sem conta; caso contrário, o T7 roda direto nas três APIs que já têm crédito.
