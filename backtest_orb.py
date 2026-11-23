#!/usr/bin/env python3
"""Teste completo do rompimento da faixa de abertura (ORB) em TODAS as ações e dias
que vieram do MetaTrader (pasta dados_mt5). Só biblioteca padrão.

Regra (a mesma das ferramentas):
  - Faixa de abertura: máxima e mínima das barras de 5 min das 10h00 às 10h15.
  - Entrada: fechamento da 1ª barra de 5 min ACIMA da máxima da faixa,
    até o limite de novas entradas (30 min antes do fim do pregão).
  - Stop: meio da faixa. Alvo: 1R (ou 2R), onde R = entrada - stop.
  - Saída: stop ou alvo, o que vier primeiro (se uma barra tocar os dois, conta o
    stop: escolha conservadora). Senão, zera no fechamento da barra que termina
    5 min antes do fim do pregão.
  - Custo por operação (ida e volta), em % do preço: --custo (padrão 0,10%:
    emolumentos + diferença de preço na execução). Imposto não incluído.

Comparação ("sem regra"): comprar SEMPRE às 10h20, com stop e alvo da mesma
distância em %, para ver se o rompimento agrega algo além de estar comprado.

  python3 backtest_orb.py                 # 1R
  python3 backtest_orb.py --alvo 2        # 2R
"""
import argparse
import collections
import datetime as dt
import glob
import json
import os
import random
import statistics


def fim_pregao(d):
    def domingo(ano, mes, n):
        x = dt.date(ano, mes, 1)
        x += dt.timedelta(days=(6 - x.weekday()) % 7)
        return x + dt.timedelta(weeks=n - 1)
    verao = domingo(d.year, 3, 2) < d <= domingo(d.year, 11, 1)
    return dt.time(16, 55) if verao else dt.time(17, 55)


def carregar(caminho):
    r = json.load(open(caminho))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    dias = collections.defaultdict(list)
    for i, t in enumerate(r["timestamp"]):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        ini = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t - 3 * 3600)  # Brasília
        fim_dia = fim_pregao(ini.date())
        if dt.time(10, 0) <= ini.time() and (ini + dt.timedelta(minutes=5)).time() <= fim_dia:
            dias[ini.date()].append((ini, o, h, l, c))
    return {d: sorted(v) for d, v in dias.items()}


def simular(barras, i_ent, entrada, stop, alvo, limite_saida):
    ultimo = entrada
    for ini, o, h, l, c in barras[i_ent + 1:]:
        if ini + dt.timedelta(minutes=5) > limite_saida:
            break
        if l <= stop:
            return min(o, stop), "stop"  # se abriu abaixo do stop, sai pior (no preço de abertura)
        if h >= alvo:
            return alvo, "alvo"
        ultimo = c
    return ultimo, "fechamento"


def operacoes(dias, alvo_r, custo):
    orb, base = [], []
    for d, b in sorted(dias.items()):
        horas = {x[0].time(): x for x in b}
        faixa = [horas.get(dt.time(10, m)) for m in (0, 5, 10)]
        if None in faixa:
            continue
        maxf, minf = max(x[2] for x in faixa), min(x[3] for x in faixa)
        fim = dt.datetime.combine(d, fim_pregao(d))
        lim_ent, lim_sai = fim - dt.timedelta(minutes=30), fim - dt.timedelta(minutes=5)
        stop = (maxf + minf) / 2
        # ORB
        for i, x in enumerate(b):
            fecha = x[0] + dt.timedelta(minutes=5)
            if x[0].time() < dt.time(10, 15) or fecha > lim_ent:
                continue
            if x[4] > maxf:
                e = x[4]
                risco = e - stop
                if risco <= 0:
                    break
                a = e + alvo_r * risco
                s, como = simular(b, i, e, stop, a, lim_sai)
                orb.append({"dia": d, "ret": (s / e - 1) - custo, "R": (s - e) / risco, "como": como,
                            "dist": risco / e})
                break
        # sem regra: compra às 10h20 (fechamento da barra das 10h15), mesma distância % do stop
        x = horas.get(dt.time(10, 15))
        if x and maxf > minf:
            e = x[4]
            dist = max((maxf - minf) / 2 / e, 0.002)
            st, a = e * (1 - dist), e * (1 + alvo_r * dist)
            i = b.index(x)
            s, como = simular(b, i, e, st, a, lim_sai)
            base.append({"dia": d, "ret": (s / e - 1) - custo, "R": (s / e - 1) / dist, "como": como})
    return orb, base


def resumo(ops):
    if not ops:
        return None
    r = [o["ret"] for o in ops]
    # intervalo de 95% do retorno médio por bootstrap, sorteando DIAS inteiros
    # (as ações se movem juntas no mesmo dia; operações do mesmo dia não são independentes)
    por_dia = collections.defaultdict(list)
    for o in ops:
        por_dia[o["dia"]].append(o["ret"])
    dias = list(por_dia)
    rng = random.Random(7)
    medias = []
    for _ in range(2000):
        amostra = [x for d in (rng.choice(dias) for _ in dias) for x in por_dia[d]]
        medias.append(sum(amostra) / len(amostra))
    medias.sort()
    return {"n": len(r), "dias": len(dias), "acerto": 100 * sum(x > 0 for x in r) / len(r),
            "media": 100 * statistics.mean(r), "ic": (100 * medias[50], 100 * medias[1949]),
            "ganho_medio": 100 * statistics.mean([x for x in r if x > 0] or [0]),
            "perda_media": 100 * statistics.mean([x for x in r if x <= 0] or [0]),
            "soma": 100 * sum(r)}


def linha(nome, s):
    if not s:
        return "%-28s sem operações" % nome
    return ("%-28s %5d ops | acerto %5.1f%% | média %+.3f%% (IC95 %+.3f a %+.3f) | ganho médio %+.2f%% "
            "| perda média %+.2f%%" % (nome, s["n"], s["acerto"], s["media"], s["ic"][0], s["ic"][1],
                                      s["ganho_medio"], s["perda_media"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="dados_mt5")
    ap.add_argument("--alvo", type=float, default=1.0, help="alvo em R (1 = 1R)")
    ap.add_argument("--custo", type=float, default=0.10, help="custo ida+volta em %% do preço")
    a = ap.parse_args()
    custo = a.custo / 100
    todos_orb, todos_base, por_acao = [], [], {}
    arquivos = sorted(f for f in glob.glob(os.path.join(a.pasta, "*.json"))
                      if not os.path.basename(f).startswith("varredura"))
    for f in arquivos:
        sym = os.path.basename(f)[:-5]
        orb, base = operacoes(carregar(f), a.alvo, custo)
        todos_orb += [dict(o, sym=sym) for o in orb]
        todos_base += base
        if orb:
            por_acao[sym] = statistics.mean(o["ret"] for o in orb)
    datas = sorted({o["dia"] for o in todos_orb})
    corte = datas[len(datas) // 2] if datas else None
    print("Rompimento da faixa de abertura | %d ações | %s a %s | alvo %.1fR | custo %.2f%% por operação"
          % (len(arquivos), datas[0] if datas else "-", datas[-1] if datas else "-", a.alvo, a.custo))
    print()
    print(linha("COM a regra (rompimento)", resumo(todos_orb)))
    print(linha("SEM regra (compra 10h20)", resumo(todos_base)))
    print()
    print(linha("Regra, 1ª metade dos dias", resumo([o for o in todos_orb if o["dia"] < corte])))
    print(linha("Regra, 2ª metade dos dias", resumo([o for o in todos_orb if o["dia"] >= corte])))
    como = collections.Counter(o["como"] for o in todos_orb)
    print()
    print("Como as operações terminaram: alvo %d | stop %d | zerou no fim do dia %d"
          % (como["alvo"], como["stop"], como["fechamento"]))
    pos = sum(v > 0 for v in por_acao.values())
    print("Ações com resultado médio positivo: %d de %d" % (pos, len(por_acao)))
    melhores = sorted(por_acao.items(), key=lambda kv: -kv[1])
    print("Melhores 5 (cuidado: no meio de 80, algumas sempre parecem boas por sorte): "
          + ", ".join("%s %+.2f%%" % (k, 100 * v) for k, v in melhores[:5]))
    print("Piores 5: " + ", ".join("%s %+.2f%%" % (k, 100 * v) for k, v in melhores[-5:]))
    print()
    print("Como ler: 'média' é o resultado médio por operação, já com custo e sem imposto.")
    print("Se o intervalo IC95 passa pelo zero, não dá para dizer que a regra ganha nem perde.")
    print("Não é recomendação de investimento.")


if __name__ == "__main__":
    main()
