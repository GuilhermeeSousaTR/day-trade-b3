# Registro de hipóteses (escrito ANTES de testar)

Cada hipótese é registrada com data, regra exata, motivo e critério de aprovação
**antes** de qualquer teste. Nada aqui é alterado depois de ver o resultado: uma
versão nova de uma ideia vira uma hipótese nova, com data nova. Reprovadas ficam
registradas.

## Regras comuns (valem para as hipóteses S1 a S3)

- **Ações:** as da lista `trader/universe.txt` com histórico disponível. Limitação
  conhecida: são empresas que existem hoje (viés de sobrevivência).
- **Dados:** fechamento diário ajustado por proventos, de 01/01/2014 até a data do teste.
- **Rebalanceamento:** no último pregão de cada mês, com pesos iguais entre as escolhidas.
- **Elegível no mês:** ação com pelo menos 13 meses de histórico e negociada nos
  últimos 5 pregões.
- **Custos:** 0,10% sobre o valor comprado ou vendido em cada rebalanceamento.
  Imposto não incluído.
- **Comparações:** (a) carteira com **todas** as elegíveis em pesos iguais, rebalanceada
  todo mês (a referência "sem estratégia"); (b) CDI.
- **Treino:** jan/2015 a dez/2019. **Teste:** jan/2020 até o último mês completo.
  O treino serve só para conferir se a ideia funcionava antes; nada é ajustado nele.
- **Aprovação:** retorno acima da referência (a) nos **dois** períodos, já com custos,
  **e**, no teste, índice de Sharpe (retorno acima do CDI dividido pelo risco) maior
  que o da referência. Passar aqui não basta para usar dinheiro: a hipótese
  aprovada ainda vai para o teste para frente.

## S1 — Momento de médio prazo (registrada em 24/11/2026)

- **Regra:** no fim de cada mês, comprar os 20% de ações elegíveis com maior retorno
  nos 12 meses anteriores, **ignorando o último mês** (retorno de t-12 a t-1).
- **Motivo:** efeito documentado em muitos mercados: o que vem subindo há meses
  tende a continuar por algum tempo, porque os investidores reagem devagar às notícias.
  O último mês é ignorado porque, no curtíssimo prazo, os preços tendem a devolver parte do movimento.

## S2 — Baixa volatilidade (registrada em 24/11/2026)

- **Regra:** no fim de cada mês, comprar os 20% de ações elegíveis com **menor**
  volatilidade dos retornos diários nos últimos 6 meses (126 pregões).
- **Motivo:** anomalia documentada: ações mais calmas costumam render, ajustado ao
  risco, tanto quanto ou mais que as agitadas, em parte porque investidores
  pagam caro pelas "loterias".

## S3 — Filtro de tendência na carteira (registrada em 24/11/2026)

- **Regra:** ficar na carteira de referência (todas as elegíveis, pesos iguais) só quando
  o valor dela, no fim do mês, estiver acima da sua média dos últimos 200 pregões;
  senão, ficar no CDI até o próximo fim de mês.
- **Motivo:** filtros de tendência costumam não aumentar muito o retorno, mas reduzir
  as grandes quedas. O critério de aprovação é o comum; além dele, olhar a maior queda.

## Resultados

| Hipótese | Data do teste | Veredito | Observação |
|---|---|---|---|
| S1 Momento | 24/11/2026 | **aprovada, evidência fraca** | +6,0 p.p./ano sobre a referência no treino e +5,7 no teste (t = 0,6 e 1,3); ganhou em 9 de 12 anos; IC95 do excesso por blocos de 6 meses: -2,7 a +11,8 p.p./ano. No teste rendeu +10,7%/ano, quase igual ao CDI (+10,1%), com queda máxima de -40,8%. Segue para teste para frente, sem dinheiro. |
| S2 Baixa volatilidade | 24/11/2026 | reprovada | -9,7 p.p./ano no treino; +3,9 no teste (t = 0,4). Menor queda máxima no teste (-26,4%), mas não passou no critério. |
| S3 Filtro de tendência | 24/11/2026 | reprovada | -2,4 p.p./ano no treino e -11,3 no teste (t = -2,5): o filtro saiu e voltou nos momentos errados, e a queda máxima no teste (-41,4%) foi maior que a da referência. |

Dados: Yahoo Finance (fechamento ajustado) e CDI do Banco Central; 82 ações com dados;
resultado completo gerado por `pesquisa_swing.py`.
