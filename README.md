# Day Trade B3: testando com dados o que os anúncios prometem

Projeto de estudo em Python que adapta para a **B3** um pacote aberto de ferramentas de
day trade e usa **dados reais** para responder a uma pergunta simples:

> As regras de "sinal de compra" vendidas em anúncios realmente ganham dinheiro depois dos custos?

**Resposta curta, com os dados até agora: não.** A regra testada ficou praticamente em
cara ou coroa e perdeu dinheiro depois dos custos. O projeto existe para medir isso com
rigor e continuar medindo, todos os dias, de forma automática.

> Projeto educacional. Não é recomendação de investimento. Nenhuma parte envia ordens reais.

---

## O que tem aqui

| Parte | O que faz |
|---|---|
| `trader-*/` | 11 ferramentas (varredura, entrada, saída, risco, orçamento, notícias, "máquina do tempo"...) adaptadas da bolsa americana para a B3: fuso de Brasília, horário do pregão que muda com o horário de verão dos EUA, feriados da B3, códigos como `PETR4`, notícias em português e nenhuma execução de ordens. |
| `mt5_ponte.py` | Ponte **somente leitura** com o MetaTrader 5: baixa barras de 5 min da corretora e detecta sozinha o fuso do servidor. |
| `yahoo_baixar.py` | Fonte alternativa gratuita (Yahoo Finance, com atraso), usada na nuvem. |
| `backtest_orb.py` | Teste completo da regra de rompimento da faixa de abertura em todas as ações e dias, com custos, comparado a "comprar sem regra". |
| `testar_filtros.py` | Testa 4 filtros **definidos antes de ver os resultados**, com período de treino e de teste separados. |
| `diario.py` | Diário de sinais: teste **para frente** (dias que nenhum teste viu), com placar acumulado. |
| `agente.py` + `.github/workflows/agentes.yml` | Agentes automáticos: no PC (Agendador do Windows + MetaTrader) e na nuvem (GitHub Actions), às 10h45 e 18h30 dos dias úteis. |
| `adaptar_b3.py` | Script que gera a versão B3 a partir do pacote original (reprodutível). |

## Metodologia

**Regra testada (rompimento da faixa de abertura):** a faixa é a máxima e a mínima das
10h00 às 10h15. A entrada é o fechamento da primeira barra de 5 min acima da máxima, com
stop no meio da faixa e alvo de 1R (também testado com 2R). Se nada acontecer, a posição
é zerada 5 min antes do fim do pregão. Quando uma barra toca stop e alvo ao mesmo tempo,
conta o stop, uma escolha conservadora.

**Cuidados contra autoengano:**
- Custo por operação de 0,10% (emolumentos + diferença de execução). Imposto não incluído.
- Comparação com uma regra "boba" (comprar sempre às 10h20 com o mesmo stop e alvo).
- Intervalo de confiança por *bootstrap* sorteando **dias inteiros**, porque as ações se
  movem juntas e operações do mesmo dia não são independentes.
- Filtros escolhidos **antes** de ver qualquer resultado e todos reportados.
- Treino e teste em períodos separados, e diário para frente a partir de 23/11/2026.
- Limitação conhecida: as ações testadas são as que existem hoje (viés de sobrevivência)
  e o histórico de 5 min tem só cerca de 4 meses.

## Resultados (dados do MetaTrader 5, 82 ações, 30/07 a 19/11/2026)

| | Operações | Acerto | Média por operação (com custo) |
|---|---|---|---|
| Regra de rompimento (1R) | 2.624 | 50,2% | **-0,08%** (IC95: -0,17% a 0,00%) |
| Sem regra (compra às 10h20) | 4.155 | 49,1% | -0,11% |
| Regra sem custos | 2.624 | 50,5% | +0,02% (IC95 cruza o zero) |

- Alvo de 2R: acerto de 38,2% e média de -0,07%.
- A regra piorou da 1ª para a 2ª metade do período (-0,03% para -0,14%).
- Só 24 das 82 ações tiveram média positiva, o que é compatível com acaso.

**Filtros (treino → teste, média por operação com custo):**

| Filtro | Treino | Teste | Passou? |
|---|---|---|---|
| Sem filtro | -0,11% | -0,12% | — |
| Mercado em alta no momento da entrada | -0,22% | -0,11% | não |
| Volume da faixa acima da média de 20 dias | -0,18% | -0,10% | não |
| Abertura sem gap de mais de 1% | -0,12% | -0,12% | não |
| Faixa mais estreita que a mediana de 20 dias | -0,09% | -0,11% | não |

Antes disso, um teste de **11.409 combinações** de estratégias simples em 15 ações
(dados diários) mostrou o mesmo padrão: as "campeãs" do treino não se distinguiram de
estratégias aplicadas a dados embaralhados, ou seja, de puro acaso.

**Conclusão:** nesses dados, a vantagem bruta da regra é menor que os custos de operar.
O diário de sinais continua medindo para frente.

## Como rodar

```bash
# Dados (escolha um)
python yahoo_baixar.py                    # Yahoo, grátis, com atraso -> pasta dados/
py -3.14 mt5_ponte.py baixar --lista      # MetaTrader 5 (Windows)   -> pasta dados_mt5/

# Testes
python backtest_orb.py --pasta dados_mt5
python testar_filtros.py --pasta dados_mt5
python diario.py --pasta dados_mt5
```

Só biblioteca padrão do Python, exceto a ponte, que usa o pacote `MetaTrader5` (Windows,
até o Python 3.14).

**Na nuvem:** o workflow `.github/workflows/agentes.yml` roda sozinho nos dias úteis
(10h45: varredura; 18h30: diário) e salva os relatórios em `relatorios/` e o placar em
`diario_sinais.csv`. Para rodar na hora: aba **Actions** → *Agentes B3* → *Run workflow*.

## Créditos

Baseado no pacote **day-trader-skill**, de Jake Schincariol (licença MIT, mantida em
`LICENSE`; o README original está em `README_original_EN.md`). A adaptação para a B3, os
testes estatísticos, o diário e os agentes são deste projeto.
