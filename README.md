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
| `mt5_ponte.py` | Ponte **somente leitura** com o MetaTrader 5: baixa barras de 5 min da corretora (inclusive anos de histórico, `historico`) e detecta sozinha o fuso do servidor. |
| `yahoo_baixar.py` | Fonte alternativa gratuita (Yahoo Finance, com atraso), usada na nuvem. |
| `backtest_orb.py` | Teste completo da regra de rompimento da faixa de abertura em todas as ações e dias, com custos, comparado a "comprar sem regra". |
| `testar_filtros.py` | Testa 4 filtros **definidos antes de ver os resultados**, com período de treino e de teste separados. |
| `diario.py` | Diário de sinais: teste **para frente** (dias que nenhum teste viu), com placar acumulado. |
| `analise_diaria.py` | Análise diária do diário: último pregão, tendência, comparação com o backtest, filtros, ações e check-up de pregões faltando (`analise/por_dia.csv`). |
| `agente.py` + `.github/workflows/agentes.yml` | Agentes automáticos: no PC (Agendador do Windows + MetaTrader) e na nuvem (GitHub Actions), às 10h45 e 18h30 dos dias úteis. |
| `arquivar_dados.py` + `historico_para_dados.py` | Banco de dados próprio: o agente da noite guarda as barras de 5 min de cada pregão em `historico/` (um `.csv.gz` por dia). O Yahoo só oferece ~60 dias; aqui o histórico cresce sem limite e pode ser convertido de volta para os testes. |
| `HIPOTESES.md` | Registro de hipóteses escrito **antes** de cada teste, com regra, motivo, critério de aprovação e veredito. |
| `pesquisa_swing.py` | Laboratório de swing (rebalanceamento mensal, ~12 anos de dados diários): testa as hipóteses S1 a S3 com treino 2015–2019 e teste 2020 em diante. |
| `HIPOTESES_DAYTRADE.md` + `pesquisa_daytrade.py` | Três hipóteses de day trade (reversão do gap, momento do dia, reversão entre ações) registradas antes do teste, com correção para múltiplos testes (IC 98,3%) e validação com dados falsos com e sem padrão. |
| `HIPOTESES_FATORES.md` + `baixar_fatores.py` + `pesquisa_fatores.py` | Fatores valor e qualidade com balanços da CVM, sem olhar o futuro (data de entrega), validados com dados falsos com e sem efeito. |
| `carteira_fatores.py` | Teste para frente mensal de F1 e F2 (baixa balanços recentes da CVM na nuvem, mede e monta carteiras no último pregão do mês). |
| `robo_demo.py` | Robô de **treino** que envia ordens **só na conta demo** (recusa conta real pelo tipo e pelo servidor): valor fixo por operação, limites de posições, entradas e perda diária, zeragem antes do fechamento, botão de parar, trava de instância única e registro do escorregamento real. Testado com um MetaTrader simulado. |
| `carteira_s1.py` | Teste para frente da S1 (Momento 12-1): no último pregão de cada mês monta a carteira e mede o mês anterior contra a referência e o CDI (`s1/`). |
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

## Pesquisa de swing (hipóteses registradas em 24/11/2026)

| Hipótese | Treino 2015–2019 | Teste 2020–2026 | Veredito |
|---|---|---|---|
| S1 Momento 12-1 (20% com maior alta em 12 meses, sem o último) | +6,0 p.p./ano | +5,7 p.p./ano | aprovada, evidência fraca |
| S2 Baixa volatilidade | -9,7 | +3,9 | reprovada |
| S3 Filtro de tendência (MM200) | -2,4 | -11,3 | reprovada |

Diferença por ano contra a carteira com todas as ações em pesos iguais, já com custos.
A S1 ganhou em 9 de 12 anos, mas o intervalo de confiança do excesso (-2,7 a +11,8 p.p./ano)
ainda inclui o zero e, no teste, ela rendeu quase o mesmo que o CDI com queda máxima de -40,8%.
Por isso segue só em **teste para frente** (`carteira_s1.py`), sem dinheiro. Detalhes em `HIPOTESES.md`.

## Pesquisa de day trade com 5 anos de dados (hipóteses registradas em 24/11/2026)

82 ações, 1.248 pregões (24/11/2021 a 24/11/2026), barras de 5 min do MetaTrader. Treino até 25/03/2025,
teste depois. Custo de 0,10% por operação; aprovação exigia IC de 98,3% (correção para 3 testes) acima de zero.

| Hipótese | Média treino | Média teste | Sem custo (teste) | Veredito |
|---|---|---|---|---|
| H1 Reversão do gap | -0,055% | -0,064% | +0,036% | reprovada |
| H2 Momento do dia | -0,097% | -0,100% | 0,000% | reprovada |
| H3 Reversão entre ações | -0,074% | -0,146% | -0,046% | reprovada |

Antes do custo, as três ficam em torno de zero; depois do custo, todas perdem. Junto com o ORB e as
11 mil combinações, a conclusão é consistente: nas ações líquidas da B3, essas regras simples de day
trade não têm vantagem. Detalhes em `HIPOTESES_DAYTRADE.md`.

## Pesquisa de fatores com balanços da CVM (hipóteses registradas em 24/11/2026)

Balanços oficiais da CVM (2010 a 2026), usados só a partir da **data de entrega** de cada documento
(sem olhar o futuro). Lucro de 12 meses montado trimestre a trimestre; escala de quantidade de ações
(unidades x milhares, misturada nos arquivos da CVM) corrigida pela plausibilidade preço/patrimônio.
Treino 2013–2019, teste 2020–2026, mesma régua da S1 (custos, referência, CDI).

| Hipótese | Treino vs referência | Teste vs referência | t no teste | Veredito |
|---|---|---|---|---|
| F1 Valor (lucro/preço) | +0,6 p.p./ano | +4,6 p.p./ano | 1,0 | aprovada, evidência fraca |
| F2 Qualidade (ROE) | +0,8 p.p./ano | +3,4 p.p./ano | 0,6 | aprovada, evidência fraca |
| F3 Valor + qualidade | −1,3 p.p./ano | +3,6 p.p./ano | 0,7 | reprovada |

No teste, nenhuma ganhou do CDI (+10,0% ao ano). F1 e F2 seguem em teste para frente
(`carteira_fatores.py`), sem dinheiro. Detalhes em `HIPOTESES_FATORES.md`.

## Como rodar

```bash
# Dados (escolha um)
python yahoo_baixar.py                    # Yahoo, grátis, com atraso -> pasta dados/
py -3.14 mt5_ponte.py baixar --lista      # MetaTrader 5 (Windows)   -> pasta dados_mt5/

# Testes
python backtest_orb.py --pasta dados_mt5
python testar_filtros.py --pasta dados_mt5
python diario.py --pasta dados_mt5
python analise_diaria.py
```

Só biblioteca padrão do Python, exceto a ponte, que usa o pacote `MetaTrader5` (Windows,
até o Python 3.14).

**Na nuvem:** o workflow `.github/workflows/agentes.yml` roda sozinho nos dias úteis
(10h45: varredura; 18h30: diário) e salva os relatórios em `relatorios/`, o placar em
`diario_sinais.csv` e as barras de cada pregão em `historico/`. Para rodar na hora: aba **Actions** → *Agentes B3* → *Run workflow*.

## Créditos

Baseado no pacote **day-trader-skill**, de Jake Schincariol (licença MIT, mantida em
`LICENSE`; o README original está em `README_original_EN.md`). A adaptação para a B3, os
testes estatísticos, o diário e os agentes são deste projeto.
