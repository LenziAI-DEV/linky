# Modelo de segurança do linky

> Visão única do que o sistema protege, de quem e como. Cada linha aponta para o código ou o ADR que decide o detalhe. Atualizada em 19/11/2026.

## O que se protege

| Ativo | Por que importa |
|---|---|
| **O perfil de Felipe no LinkedIn** | Um post errado ou injetado sai em nome dele. É o ativo mais sensível |
| **A VPS** | Roda também outro sistema em produção. O linky não pode derrubá-lo nem abrir caminho até ele |
| **Chaves de API e o token do LinkedIn** | Dão gasto e publicação |
| **O orçamento** | Teto rígido de US$ 3/mês |
| **A fila editorial** (SQLite no volume `linky_data`) | Guarda as pautas, os posts aprovados e o histórico das decisões |

## Entradas não confiáveis

| Entrada | Risco | Defesa | Onde |
|---|---|---|---|
| Texto das notícias (feeds e páginas) | Injeção de prompt: o texto tenta mandar no agente | O texto da web entra no fim do prompt, delimitado em `<documentos_nao_confiaveis>`, e não consegue abrir nem fechar o delimitador. A saída do modelo só vale se respeitar o contrato tipado. E nada é publicado sem Felipe aprovar o texto e a imagem exatos | `harness/prompt.py`, `prompts/README.md`, ADR 0005 |
| Links das notícias e os redirecionamentos deles | SSRF: alcançar o n8n, o próprio serviço, o metadata da nuvem ou a rede interna | `netguard.check_url` antes de cada requisição e de cada redirecionamento (seguidos à mão, até 5): só http/https nas portas 80/443, sem usuário na URL, sem nome de serviço Docker nem `localhost`, e todo IP resolvido tem de ser público. Só HTML ou texto, com o corpo cortado em 3 MB e o texto no limite de tokens da redação | `netguard.py`, `agents/post.py` |
| Formulários das decisões (webhook público do n8n) | Decisão forjada, reenvio, robô que abre o link | O GET nunca muda nada (scanners podem abrir). O POST exige um token HMAC por pauta, derivado do segredo do serviço, que vale uma vez. Toda decisão muda a versão da pauta, então um reenvio é recusado. O padrão de cada pauta é "não decidir agora" | `service/forms.py`, ADR 0005 |
| Pedido de post por e-mail (desenhado, não construído) | Remetente forjado | Só um remetente, com `dkim=pass` e `dmarc=pass` no veredito do Resend e a assinatura do webhook conferida. Os outros são ignorados em silêncio | ADR 0008 |

## Superfície de rede

- **O serviço `linky-agents` não tem porta publicada nem rota no proxy.** Só o n8n o alcança, pela rede interna, e cada chamada leva o cabeçalho `X-Linky-Token`, comparado em tempo constante (`service/app.py`, ADR 0003).
- **Saída para a internet por uma rede própria (`linky_egress`)**, separada da rede interna do n8n, que não tem gateway. O deploy confere que o container alcança as APIs dos modelos (`ops/linky/check-egress.sh`, incidente de 17/11).
- **Container endurecido:** usuário sem privilégio, sistema de arquivos só leitura, `cap_drop: ALL`, `no-new-privileges`, 256 MB sem swap (`ops/linky/compose.yaml`).

## Segredos

- **Nada de segredo no repositório.** As chaves dos modelos e o token do serviço ficam num `.env` na VPS (modo 600) e entram no container por variável de ambiente. As credenciais do LinkedIn e do Resend ficam no cofre do n8n, cada uma restrita aos domínios que usa.
- **As chaves nunca vão para o registro nem para o ledger.** Há teste para isso (`tests/test_harness_providers.py`, que usa uma chave falsa, ignorada no `.gitleaksignore` do público).
- **O código na VPS vem por uma deploy key só de leitura.**
- **Varredura:** gitleaks no histórico e na árvore e trivy (vulnerabilidades, configuração, segredos) antes de cada publicação do retrato público (ADR 0010).

## Custo e abuso

- Toda chamada paga entra no ledger com o preço do modelo. Há tetos por execução, por dia e por mês (US$ 3). Antes de cada chamada, o ledger calcula o pior caso: a chamada que poderia estourar um teto não é feita e vira alerta por e-mail (`harness/budget.py`, `harness/ledger.py`, `config/models.yaml`).
- Uma fonte ruim ou um modelo que falha não derruba a esteira: há fallback entre modelos e um alerta quando a cadeia toda falha.

## Publicação

- **Nada sai sem o "aprovar" de Felipe** para aquele texto e aquela imagem. Se o post mudar depois da aprovação (pedido de ajuste), a aprovação vale de novo só para a nova versão.
- **Modo sombra** (`LINKY_SHADOW`) para ensaiar sem publicar: a publicação manda só o e-mail "Publicaria agora" (ADR 0004).

## Dados pessoais

- O repositório público não tem e-mail, domínio, IP nem perfil reais: o script de exportação troca tudo e falha se sobrar algo (ADR 0010).
- O coletor de métricas (ADR 0009), que usa a conta pessoal de Felipe, fica só no repositório privado.

## Riscos conhecidos e aceitos

| Risco | Por que se aceita |
|---|---|
| **DNS rebinding** entre a checagem do `netguard` e a conexão | O atacante precisaria controlar o DNS de um link que a curadoria escolheu. O texto só chega à redação, e nada sai sem aprovação |
| **Webhook dos formulários público** | Sem o token HMAC de uso único, ele não decide nada. É o preço de não ter interface própria |
| **VPS dividida com outro sistema** | Limites de memória e rede isolam o linky, e o deploy só recria o próprio container |

## Achou uma falha?

Use o reporte privado de vulnerabilidade do GitHub (aba Security do repositório) ou fale com Felipe diretamente. Não abra issue pública com detalhes de exploração.
