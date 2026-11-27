# Hipóteses de day trade registradas ANTES do teste

Registradas em **24/11/2026**, antes de baixar o histórico longo do MetaTrader e antes de rodar
qualquer teste destas regras. Nada aqui pode ser mudado depois de ver os resultados; uma ideia
nova vira uma hipótese nova, com data nova.

Por que registrar antes: testamos 11.409 combinações e nenhuma passou. Quem testa muitas regras
sempre acha alguma que "funcionou" por sorte. Fixar poucas regras, com motivo, antes de olhar os
dados, é o que separa pesquisa de garimpo.

## Regras comuns às três

- **Ações:** as de `trader/universe.txt` que vierem no histórico longo do MetaTrader
  (`mt5_ponte.py historico`). Atenção: são as ações líquidas de HOJE; empresas que sumiram da
  bolsa não estão (viés de sobrevivência, que favorece os resultados).
- **Barras:** 5 minutos, horário de Brasília. Pregão das 10h00 até o fim (17h55, ou 16h55 com
  horário de verão nos EUA). Dias sem a barra das 10h00 (ex.: Quarta-feira de Cinzas) ficam fora.
- **Fechamento anterior:** fechamento da última barra do pregão anterior da mesma ação.
- **Venda a descoberto:** permitida (no day trade da B3 não há aluguel de ação).
- **Custo:** 0,10% do preço por operação, ida e volta (o mesmo do teste do ORB). Também mostramos
  0,05% e 0,20%, só como informação.
- **Preenchimento conservador:** se a mesma barra toca o stop e o alvo, conta o stop; se a barra
  abre além do stop, sai no preço de abertura.
- **Treino e teste:** os dias (de calendário, iguais para todas as ações) são divididos em
  2/3 iniciais = treino e 1/3 final = teste.
- **Intervalo de confiança:** bootstrap sorteando DIAS inteiros (as ações se movem juntas no mesmo
  dia), 2.000 sorteios.

## Regra de aprovação (para cada hipótese)

Aprovada só se TODAS valerem:

1. Média por operação, já com custo de 0,10%, **acima de zero no treino E no teste**.
2. No teste, o **limite de baixo do intervalo de 98,3%** fica acima de zero
   (98,3% = 95% corrigido para 3 hipóteses testadas, correção de Bonferroni).
3. Pelo menos **300 operações no teste**.

Aprovada significa só "merece ir para o teste para frente na conta demo". Não significa dinheiro
de verdade.

## H1. Reversão do gap

**Ideia:** quando a ação abre muito longe do fechamento anterior (gap), parte desse salto costuma
ser exagero e o preço volta.

- `gap = abertura da barra das 10h00 / fechamento anterior - 1`.
- Só dias com **1% ≤ |gap| ≤ 5%**.
- **Entrada:** no fechamento da barra das 10h00 (10h05), **contra o gap**: gap para cima → vende;
  gap para baixo → compra.
- **Alvo:** o fechamento anterior (o gap "fecha").
- **Stop:** a mesma distância do alvo, do outro lado da entrada (1 para 1).
- Se a entrada já estiver além do fechamento anterior, não opera.
- **Saída:** alvo, stop ou o fechamento da barra que termina 5 min antes do fim do pregão.

## H2. Momento do dia (o começo prevê o fim)

**Ideia:** estudos em vários mercados (ex.: Gao, Han, Li e Zhou, 2018) acham que o rumo da
primeira meia hora tende a se repetir na última meia hora, quando fundos ajustam posições.

- `r1 = fechamento da barra das 10h25 (às 10h30) / fechamento anterior - 1`.
- Só dias com **|r1| ≥ 0,5%**.
- **Entrada:** no fechamento da barra que termina 30 min antes do fim do pregão, **na direção de
  r1** (positivo → compra; negativo → vende).
- **Saída:** fechamento da barra que termina 5 min antes do fim do pregão. Sem stop e sem alvo.

## H3. Reversão entre ações na primeira hora

**Ideia:** as ações que mais subiram (ou caíram) na primeira hora, em relação às outras, tendem a
devolver parte do movimento no resto do dia (exagero de curto prazo).

- Às 11h00 (fechamento da barra das 10h55), retorno de cada ação desde a abertura das 10h00.
- Só dias com pelo menos **20 ações** com dados.
- **Compra** os 10% piores e **vende** os 10% melhores (arredondando para baixo, mínimo 2 de cada
  lado). Entrada no fechamento da barra das 10h55.
- **Saída:** fechamento da barra que termina 5 min antes do fim do pregão. Sem stop e sem alvo.
- Cada ação é uma operação.

## Resultados

Rodado em **24/11/2026** com `pesquisa_daytrade.py` sobre o histórico do MetaTrader (Clear, conta demo):
82 ações, 1.248 pregões de 24/11/2021 a 24/11/2026, barras de 5 min. Treino até 25/03/2025, teste de
26/03/2025 a 24/11/2026. Nada acima foi alterado depois de ver os números.

| Hipótese | Operações (treino / teste) | Média treino | Média teste | IC 98,3% teste | Sem custo (teste) | Veredito |
|---|---|---|---|---|---|---|
| H1 Reversão do gap | 4.724 / 2.653 | -0,055% | -0,064% | -0,164% a +0,030% | +0,036% | REPROVADA |
| H2 Momento do dia | 29.617 / 14.792 | -0,097% | -0,100% | -0,114% a -0,085% | 0,000% | REPROVADA |
| H3 Reversão entre ações | 9.270 / 4.472 | -0,074% | -0,146% | -0,222% a -0,074% | -0,046% | REPROVADA |

**Leitura:** antes do custo, as três ficam praticamente em zero (H2 exatamente zero em quase 45 mil
operações). O custo de 0,10% por operação vira perda certa. Mesmo com metade do custo (0,05%), todas
ficam negativas no teste. Nos 5 anos, nenhuma das três mostra vantagem sobre o acaso no day trade das
ações líquidas da B3.

Consequência: nenhuma regra vai para o robô da conta demo, e não vale pagar servidor para rodá-lo.
O teste para frente do rompimento da abertura (diário na nuvem) continua, e a carteira mensal S1
(`HIPOTESES.md`) segue como a única ideia com algum sinal, ainda fraco.
