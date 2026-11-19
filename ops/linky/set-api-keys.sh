#!/usr/bin/env bash
# Grava as chaves de API dos agentes (e a do n8n) na VPS, sem eco na tela.
# Rodar na VPS como o usuário de deploy:  ssh -t vps ./linky-api-keys.sh
# Cada pergunta aceita Enter vazio para manter a chave que já está lá. Depois de gravar,
# confere cada chave com uma chamada que não gasta nada (lista de modelos) e mostra só o
# código HTTP. As chaves dos agentes vão para /opt/linky/.env (lido pelo linky-agents no
# próximo deploy); a do n8n vai para /opt/linky/n8n-api.env (usada para ativar workflows).
set -euo pipefail
umask 077
ENV=/opt/linky/.env
N8N_ENV=/opt/linky/n8n-api.env

put() {  # put <arquivo> <NOME> <valor>: troca ou acrescenta a linha NOME=valor
  local f="$1" name="$2" value="$3" tmp
  tmp="$(mktemp "${f}.XXXX")"
  { [ -f "$f" ] && grep -v "^${name}=" "$f" || true; } >"$tmp"
  printf '%s=%s\n' "$name" "$value" >>"$tmp"
  mv "$tmp" "$f"
  chmod 600 "$f"
}

ask() {  # ask <rótulo> <prefixo esperado>: lê sem eco; vazio = manter
  local label="$1" prefix="$2" v
  read -rsp "${label} (Enter para manter): " v
  echo >&2
  if [ -n "$v" ] && [ "${v#"$prefix"}" = "$v" ]; then
    echo "  não começa com ${prefix}; ignorada." >&2
    v=""
  fi
  printf '%s' "$v"
}

openai="$(ask "Chave da OpenAI (sk-...)" "sk-")"
anthropic="$(ask "Chave da Anthropic (sk-ant-...)" "sk-ant-")"
n8n="$(ask "Chave da API do n8n (eyJ...)" "eyJ")"

[ -n "$openai" ] && put "$ENV" OPENAI_API_KEY "$openai"
[ -n "$anthropic" ] && put "$ENV" ANTHROPIC_API_KEY "$anthropic"
[ -n "$n8n" ] && put "$N8N_ENV" N8N_API_KEY "$n8n"
unset openai anthropic n8n

get() { grep -s "^$2=" "$1" | head -1 | cut -d= -f2-; }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@" || echo "falhou"; }

echo "Conferindo (200 = ok):"
k="$(get "$ENV" OPENAI_API_KEY)"
[ -n "$k" ] && echo "  OpenAI:    $(code -H "Authorization: Bearer $k" https://api.openai.com/v1/models)"
k="$(get "$ENV" ANTHROPIC_API_KEY)"
[ -n "$k" ] && echo "  Anthropic: $(code -H "x-api-key: $k" -H 'anthropic-version: 2023-06-01' https://api.anthropic.com/v1/models)"
k="$(get "$N8N_ENV" N8N_API_KEY)"
[ -n "$k" ] && echo "  n8n:       $(code -H "X-N8N-API-KEY: $k" 'https://n8n.example.com/api/v1/workflows?limit=1')"
unset k
echo "Pronto. Pode fechar esta aba."
