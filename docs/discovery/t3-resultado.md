# T3: publicação pela API do LinkedIn (resultado, 06/11/2026)

**Status: ✅ validado.** O primeiro post real foi publicado pelo sistema: `urn:li:share:7524345177881194496`, com a legenda da calibração 01 (1.217 caracteres) e a imagem do layout **contraste**, com visibilidade pública.

## O que foi confirmado

| Hipótese | Resultado |
|---|---|
| H1: app self-service com `w_member_social` publica com imagem no perfil pessoal via `/rest/posts` | ✅ Confirmado: `POST /rest/posts` → 201, com `LinkedIn-Version: 202610` e autor `urn:li:person:{sub}` |
| Upload de imagem com dono pessoa (`/rest/images?action=initializeUpload` + `PUT` no `uploadUrl`) | ✅ 201, imagem `urn:li:image:…`, publicada sem precisar esperar processamento |
| Exigência de Página vinculada ao app | ✅ Confirmada. Foi criada a Página **Lenzia** (`linkedin.com/company/lenziaai`), usada só como “dona” do app |
| Formatação | ✅ Quebras de linha, listas com `•` e `→`, e hashtags clicáveis renderizam corretamente. A imagem 4:5 aparece inteira no feed |

## Configuração resultante

- **App:** Lenzi Content Pipeline (ID 265077601), com os produtos Share on LinkedIn (Default Tier) e Sign In with OpenID Connect (Standard Tier).
- **Escopos:** `openid`, `profile`, `email`, `w_member_social`.
- **Redirect:** `https://n8n.example.com/rest/oauth2-credential/callback`.
- **Credencial no n8n:** “LinkedIn account” (`linkedInOAuth2Api`), restrita aos domínios `api.linkedin.com` e `www.linkedin.com`.
- **Token:** 60 dias, sem refresh token. A reconexão é manual no n8n e precisa de lembrete automático no MVP.
- **Workflows de teste** (inativos, em `n8n/`): `t3-leitura-perfil.json` e `t3-publicacao-airbnb.json`.

## Aprendizados para o MVP

- A execução pelo CLI (`n8n execute`) dentro do container exige `N8N_RUNNERS_BROKER_PORT` diferente do da instância principal. No MVP, o disparo será por gatilhos do próprio n8n (agenda e formulário), não pelo CLI.
- O texto do post passa pelo formato *little* do LinkedIn. Os caracteres `\ | { } @ [ ] ( ) < > * _ ~` precisam de escape, e o redator ou o publicador deve tratar isso. A legenda testada não tinha nenhum deles.
- As imagens precisam estar em `/home/node/.n8n-files/` para o nó de leitura de arquivo do n8n 2.x.
