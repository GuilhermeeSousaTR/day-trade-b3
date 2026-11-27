# Hipóteses de fatores (balanços) registradas ANTES do teste

Registradas em **24/11/2026**, antes de baixar qualquer balanço da CVM e antes de rodar qualquer
teste destas regras. Nada aqui é mudado depois de ver os resultados.

Por que fatores: nos testes de day trade (ORB, 11 mil combinações, H1 a H3) nada sobreviveu ao
custo. Em prazos mensais o custo pesa pouco, e a pesquisa acadêmica documenta em vários países
que ações baratas em relação ao lucro (valor) e empresas muito rentáveis (qualidade) tendem a
render acima da média ao longo de anos. A pergunta aqui é se isso aparece nas ações líquidas da B3.

## Regras comuns (iguais às de S1 a S3 em `HIPOTESES.md`, mais o que é próprio de balanço)

- **Ações:** as de `trader/universe.txt` com preços e balanços disponíveis. Viés de sobrevivência:
  são empresas que existem hoje, o que favorece os resultados.
- **Balanços:** dados abertos da CVM (ITR trimestral e DFP anual), demonstração **consolidada**
  (se a empresa não publicar consolidada, a individual).
- **Sem olhar o futuro:** um balanço só pode ser usado a partir da **data em que foi entregue à
  CVM** (`DT_RECEB`). Se houver reapresentação, vale a versão entregue até o dia do rebalanceamento.
- **Lucro de 12 meses (LL12):** lucro líquido atribuído aos controladores (se não houver essa
  linha, o lucro líquido do período), somando os últimos 4 trimestres:
  último exercício anual + acumulado do ano atual − acumulado do mesmo período do ano anterior.
- **Patrimônio líquido (PL):** atribuído aos controladores (se não houver, o total), do último
  balanço entregue.
- **Número de ações:** total do capital menos ações em tesouraria, do último documento entregue.
- **Valor de mercado:** fechamento do dia (sem ajuste por dividendos, corrigido por desdobramentos e
  grupamentos) × número de ações. Limitação: empresas com ações ON e PN usam o preço da classe da lista.
- **Balanço velho:** se o último balanço entregue tiver data de referência com mais de 7 meses,
  a ação fica fora das carteiras de F1 a F3 naquele mês.
- **Preços, rebalanceamento, custos e referência:** iguais a S1 a S3 (fechamento ajustado, último
  pregão do mês, pesos iguais, 0,10% sobre o valor girado, referência = todas as elegíveis por preço
  em pesos iguais, e o CDI).
- **Treino:** jan/2013 a dez/2019. **Teste:** jan/2020 até o último mês completo (mesmo teste da S1,
  para comparar).
- **Aprovação:** retorno acima da referência nos **dois** períodos, já com custos, **e**, no teste,
  Sharpe maior que o da referência (a mesma regra de S1 a S3).
- **Força da evidência:** contando S1 a S3 e F1 a F3, são 6 hipóteses mensais testadas. Por isso a
  evidência só é chamada de **forte** se, no teste, a estatística t do excesso mensal sobre a
  referência passar de **2,64** (5% corrigido para 6 testes, correção de Bonferroni). Abaixo disso,
  uma aprovação é **evidência fraca** e só vai para o teste para frente.

## Ajustes de dados (26/11/2026, depois do download e ANTES de rodar qualquer teste)

Ao abrir os arquivos da CVM apareceram três limitações de dados. As regras acima não mudam; muda só
como os números são obtidos:

1. **Quantidade de ações:** os arquivos de composição do capital só existem a partir de 2020. Antes disso,
   a quantidade é estimada por lucro do período ÷ lucro por ação do mesmo documento.
2. **Escala misturada (unidades x milhares):** tanto a quantidade oficial de ações quanto o lucro por
   ação aparecem ora em unidades, ora em milhares, conforme a empresa e o ano, sem coluna que avise
   (ex.: Itaú com 11 milhões de ações, quando são cerca de 11 bilhões). Como o erro é sempre de 1.000
   vezes, a escala (x1000, x1 ou ÷1000) é escolhida pela que deixa o valor de mercado ÷ patrimônio mais
   perto de 2 (se o patrimônio for negativo, o P/L mais perto de 10). Uma escala errada daria
   0,002 ou 2.000 vezes o patrimônio, então não há ambiguidade. Sem lucro por ação, usa-se a
   quantidade oficial mais antiga ajustada por desdobramentos e grupamentos.
3. **Versões dos balanços:** a CVM guarda nos arquivos só a versão mais recente de cada balanço. Para não
   olhar o futuro, cada número só vale a partir da data de entrega dessa versão; enquanto ela não
   existe, vale o balanço anterior (se não tiver mais de 7 meses).

## F1. Valor (lucro sobre preço)

- **Regra:** no fim de cada mês, entre as elegíveis com LL12 positivo, comprar os 20% com maior
  **LL12 / valor de mercado** (o inverso do P/L), mínimo 5 ações.
- **Motivo:** ações baratas em relação ao lucro costumam estar baratas por pessimismo exagerado;
  é um dos efeitos mais estudados em finanças.

## F2. Qualidade (rentabilidade)

- **Regra:** no fim de cada mês, entre as elegíveis com LL12 e PL positivos, comprar os 20% com
  maior **ROE = LL12 / PL**, mínimo 5 ações.
- **Motivo:** empresas que geram muito lucro por real investido tendem a ser subestimadas pelo mercado.

## F3. Valor + qualidade ("fórmula mágica" simplificada)

- **Regra:** entre as elegíveis com LL12 e PL positivos, ordenar por F1 e por F2 separadamente,
  somar as duas posições, e comprar os 20% com a menor soma (melhores nas duas), mínimo 5 ações.
- **Motivo:** combina "barata" com "boa", para evitar empresas baratas porque são ruins
  (ideia popularizada por Joel Greenblatt; aqui com lucro e PL no lugar de EBIT e capital investido).

## Resultados

Rodado em **26/11/2026** com `pesquisa_fatores.py`: balanços da CVM de 2010 a 2026 (78 empresas com
balanço utilizável), preços do Yahoo e CDI do Banco Central. Treino jan/2013 a dez/2019 (84 meses),
teste jan/2020 a nov/2026 (83 meses). Nada acima foi mudado depois de ver os números.

| Hipótese | Treino 2013–2019 | Teste 2020– | t no teste | Veredito |
|---|---|---|---|---|
| Referência (todas) | +19,7% a.a. | +4,9% a.a. | | |
| CDI | +9,6% a.a. | +10,0% a.a. | | |
| F1 Valor | +20,3% a.a. (+0,6 p.p.) | +9,5% a.a. (+4,6 p.p.) | +1,0 | **aprovada, evidência fraca** |
| F2 Qualidade | +20,5% a.a. (+0,8 p.p.) | +8,3% a.a. (+3,4 p.p.) | +0,6 | **aprovada, evidência fraca** |
| F3 Valor + qualidade | +18,4% a.a. (−1,3 p.p.) | +8,5% a.a. (+3,6 p.p.) | +0,7 | reprovada (perdeu no treino) |

**Leitura honesta:**
- F1 e F2 passaram na regra registrada, mas por pouco: no treino ganharam menos de 1 p.p. por ano, e no
  teste a estatística t (1,0 e 0,6) está longe dos 2,64 exigidos para evidência forte. A diferença ainda
  pode ser sorte.
- No teste, **nenhuma das três ganhou do CDI** (F1 +9,5% contra CDI +10,0% ao ano), com quedas máximas
  perto de −38%.
- F2 teve a menor queda no treino (−17,5% contra −33,4% da referência), o que sugere menos risco, mas
  isso não fazia parte do critério.

Consequência: F1 e F2 vão para o **teste para frente** (`carteira_fatores.py`, todo fim de mês,
junto com a S1), sem dinheiro. Conclusão só depois de 12 a 24 meses.
