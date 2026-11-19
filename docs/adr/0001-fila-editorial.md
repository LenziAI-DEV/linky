# ADR 0001: fila editorial com horários fixos e validade de pauta

- **Status:** aceita · **Data:** 06/11/2026 · **Decisores:** Felipe Lenzi (produto), Claude (arquitetura)

## Contexto

A v1.1 do PRD acoplava duas decisões: escolher a pauta e publicar o post. Felipe levantou situações reais que esse desenho não atende:

- gosta de uma pauta na terça, mas não quer postar dois dias seguidos e prefere publicar na quarta;
- gosta de pautas em vários dias seguidos e precisa distribuí-las pela semana;
- gosta de duas pautas no mesmo dia;
- passa dias sem gostar de nenhuma;
- não abre o e-mail no dia.

Decisões de Felipe em 06/11: publicação **fixa às segundas, quartas e sextas, às 18:30**, no máximo 1 post por dia. Sábado sem pautas. Domingo às 21:00, 5 pautas cobrindo sexta, sábado e domingo.

## Decisão

1. **Uma fila editorial** em que cada pauta é uma entrada com estados explícitos: proposta, banco, escolhida, aguardando aprovação, aprovada, publicada, falhou, vencida e descartada. Os estados são validados em código.
2. **A pauta reserva o horário quando é escolhida**, no "próximo horário livre" ou numa data definida por Felipe. Dois posts nunca disputam o mesmo dia.
3. **Validade por pauta, a partir da data do fato:** perecível vale 4 dias, duradoura vale 14. Escolher para uma data posterior à validade é recusado.
4. **Nada é publicado sem aprovação.** Sem aprovação até o prazo (16:30 do dia do horário), o post é adiado para o próximo horário livre dentro da validade, ou vence.
5. **Antecipação só para posts aprovados e flexíveis.** Um horário vazio puxa um post aprovado como "próximo horário livre"; data escolhida por Felipe é respeitada.
6. **Repescagem e modo silencioso** para e-mails não vistos (ver PRD §7.6).
7. **Onde mora:** no harness (`src/linky_agents/editorial.py` + `config/editorial.yaml`), persistido em SQLite. O n8n só aciona: relógio de hora em hora (`tick`), envio de pautas (`proposal_plan`) e publicação (`due`).

## Alternativas consideradas

| Alternativa | Por que não |
|---|---|
| Lógica nos workflows do n8n (IF, Wait, Data Tables) | Regras de calendário e validade espalhadas em JSON de workflow, sem teste unitário. Cada caso novo vira um nó a mais. É o mesmo argumento da D17 |
| Postgres do n8n | Acopla o harness ao banco de produção de outro projeto. Um SQLite no volume do harness é suficiente para dezenas de entradas por mês |
| Agendamento nativo do LinkedIn | A API não oferece agendamento para perfil pessoal, e mudar uma data exigiria apagar e recriar o post |
| Publicar no ato da aprovação | Era o desenho da v1.1. Não atende a cadência fixa nem a distribuição pela semana |

## Consequências

- **Positivas:** cadência previsível de 3 posts por semana. Nenhum e-mail perdido custa uma boa pauta enquanto ela valer. As regras ficam testadas (19 casos, incluindo os cenários levantados por Felipe) e mudam por configuração, não por código.
- **Negativas:** há um estado a mais para operar e fazer backup (o arquivo `editorial.db`, que entra na rotina de backup da VPS). O e-mail da decisão 1 fica mais rico, com seleção múltipla, data e banco, e precisa ser validado no T4′.
- **No T2:** a fila é operada à mão nesta conversa, seguindo as mesmas regras. A publicação usa `ops/publish-once.sh` agendado no horário fixo.
