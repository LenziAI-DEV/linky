# Prompts versionados dos agentes

Cada agente tem uma pasta com um arquivo por versão: `prompts/<agente>/<versão>.md` (ex.: `prompts/triagem/v1.md`). O harness (`linky_agents.harness`) grava em cada execução o ID (`triagem/v1`), a versão e o SHA-256 do arquivo.

**Regras**

- **Nunca edite uma versão já usada em produção.** Crie a próxima (`v2.md`) e troque a versão no `AgentSpec` do agente. Assim, todo registro de execução aponta para um texto que ainda existe.
- O arquivo é a **parte fixa** do prompt. O harness acrescenta, ainda na parte fixa, o JSON Schema da saída e a regra de segurança sobre texto da web. A **parte variável** (a entrada da execução) vai no fim, na mensagem do usuário. Essa ordem aproveita o cache de prefixo dos fornecedores.
- Não escreva dados da execução no arquivo (datas, notícias, nomes). Tudo o que muda entre execuções entra pela entrada tipada do agente.
- Texto vindo da web chega delimitado em `<documentos_nao_confiaveis>`. O prompt não precisa repetir a regra, mas pode reforçá-la.
- Mudou um prompt? Ele só entra se a nota do gold set não cair (PRD §7.4, item 6).

Os prompts finais da triagem, da curadoria, da redação, da checagem e da direção de arte dependem do T2 (a partir de ~13/11/2026).
