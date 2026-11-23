#!/usr/bin/env python3
"""Testa FILTROS PRÉ-DEFINIDOS no rompimento da faixa de abertura (dados_mt5).

Os 4 filtros foram escolhidos ANTES de ver os resultados e são todos reportados,
funcionem ou não (escolher só o que "deu certo" seria a mesma armadilha do robô
de 10 mil estratégias):

  F1 mercado_em_alta : no momento da entrada, a ação típica (mediana de todas)
                       está acima da abertura do dia.
  F2 volume_alto     : volume da faixa de abertura acima da média dos 20 dias anteriores.
  F3 sem_gap         : abertura a menos de 1% do fechamento do dia anterior.
  F4 faixa_estreita  : faixa de abertura (em %) menor que a mediana dos 20 dias anteriores.

Treino = 1ª metade dos dias; teste = 2ª metade. Um filtro só "passa" se melhorar a
regra nos DOIS períodos e ficar positivo no teste depois dos custos.
"""
import argparse
import collections
import datetime as dt
import glob
import os
import json
import statistics

from backtest_orb import carregar, fim_pregao, linha, resumo, simular

FILTROS = ["mercado_em_alta", "volume_alto", "sem_gap", "faixa_estreita"]


def coletar(pasta, alvo_r, custo):
    arquivos = sorted(f for f in glob.glob(os.path.join(pasta, "*.json"))
                      if not os.path.basename(f).startswith(("varredura", "agora")))
    dados = {os.path.basename(f)[:-5]: carregar(f) for f in arquivos}
    vols = {}
    for sym, dias in dados.items():  # volumes por barra vêm do arquivo original
        r = json.load(open(os.path.join(pasta, sym + ".json")))["chart"]["result"][0]
        v = {}
        for t, vol in zip(r["timestamp"], r["indicators"]["quote"][0]["volume"]):
            v[dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t - 3 * 3600)] = vol or 0
        vols[sym] = v
    # "mercado": retorno de cada ação desde a abertura, a cada horário -> mediana
    mov = collections.defaultdict(list)
    for sym, dias in dados.items():
        for d, b in dias.items():
            if b and b[0][0].time() == dt.time(10, 0):
                ab = b[0][1]
                for x in b:
                    mov[(d, x[0].time())].append(x[4] / ab - 1)
    mercado = {k: statistics.median(v) for k, v in mov.items() if len(v) >= 20}

    ops = []
    for sym, dias in dados.items():
        hist_vol, hist_larg, fech_ant = [], [], None
        for d in sorted(dias):
            b = dias[d]
            horas = {x[0].time(): x for x in b}
            faixa = [horas.get(dt.time(10, m)) for m in (0, 5, 10)]
            if None in faixa:
                fech_ant = b[-1][4] if b else fech_ant
                continue
            maxf, minf = max(x[2] for x in faixa), min(x[3] for x in faixa)
            ab = faixa[0][1]
            larg = (maxf - minf) / ab
            vol_f = sum(vols[sym].get(x[0], 0) for x in faixa)
            gap = abs(ab / fech_ant - 1) if fech_ant else None
            fim = dt.datetime.combine(d, fim_pregao(d))
            lim_ent, lim_sai = fim - dt.timedelta(minutes=30), fim - dt.timedelta(minutes=5)
            stop = (maxf + minf) / 2
            for i, x in enumerate(b):
                if x[0].time() < dt.time(10, 15) or x[0] + dt.timedelta(minutes=5) > lim_ent:
                    continue
                if x[4] > maxf:
                    e = x[4]
                    risco = e - stop
                    if risco > 0 and len(hist_vol) >= 20:
                        s, como = simular(b, i, e, stop, e + alvo_r * risco, lim_sai)
                        m = mercado.get((d, x[0].time()))
                        ops.append({"dia": d, "sym": sym, "ret": (s / e - 1) - custo, "como": como,
                                    "hora": x[0] + dt.timedelta(minutes=5), "entrada": e, "stop": stop,
                                    "alvo": e + alvo_r * risco, "saida": s,
                                    "mercado_em_alta": m is not None and m > 0,
                                    "volume_alto": vol_f > statistics.mean(hist_vol[-20:]),
                                    "sem_gap": gap is not None and gap < 0.01,
                                    "faixa_estreita": larg < statistics.median(hist_larg[-20:])})
                    break
            hist_vol.append(vol_f)
            hist_larg.append(larg)
            fech_ant = b[-1][4]
    return ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="dados_mt5")
    ap.add_argument("--alvo", type=float, default=1.0)
    ap.add_argument("--custo", type=float, default=0.10)
    a = ap.parse_args()
    ops = coletar(a.pasta, a.alvo, a.custo / 100)
    if not ops:
        raise SystemExit("Sem operações: baixe mais dias de dados (a regra precisa de 20 dias de histórico).")
    datas = sorted({o["dia"] for o in ops})
    corte = datas[len(datas) // 2]
    tr = [o for o in ops if o["dia"] < corte]
    te = [o for o in ops if o["dia"] >= corte]
    print("Filtros no rompimento | treino %s a %s | teste %s a %s | alvo %.0fR | custo %.2f%%"
          % (datas[0], datas[len(datas) // 2 - 1], corte, datas[-1], a.alvo, a.custo))
    base_tr, base_te = resumo(tr), resumo(te)
    print()
    print("TREINO")
    print(linha("sem filtro", base_tr))
    for f in FILTROS:
        print(linha(f, resumo([o for o in tr if o[f]])))
    print(linha("todos os 4 juntos", resumo([o for o in tr if all(o[f] for f in FILTROS)])))
    print()
    print("TESTE (período não usado para decidir nada)")
    print(linha("sem filtro", base_te))
    for f in FILTROS:
        print(linha(f, resumo([o for o in te if o[f]])))
    print(linha("todos os 4 juntos", resumo([o for o in te if all(o[f] for f in FILTROS)])))
    print()
    print("VEREDITO (passa = melhora no treino E no teste E fica positivo no teste, já com custo):")
    for f in FILTROS + ["todos"]:
        sel = (lambda o: all(o[x] for x in FILTROS)) if f == "todos" else (lambda o, f=f: o[f])
        s_tr, s_te = resumo([o for o in tr if sel(o)]), resumo([o for o in te if sel(o)])
        if not s_tr or not s_te or s_te["n"] < 30:
            print("  %-18s poucas operações para concluir" % f)
            continue
        passa = (s_tr["media"] > base_tr["media"] and s_te["media"] > base_te["media"] and s_te["media"] > 0)
        forte = passa and s_te["ic"][0] > 0
        print("  %-18s %s (treino %+.3f%%, teste %+.3f%%, IC95 do teste %+.3f a %+.3f)"
              % (f, "PASSA com evidência forte" if forte else ("passa, mas evidência fraca" if passa else "não passa"),
                 s_tr["media"], s_te["media"], s_te["ic"][0], s_te["ic"][1]))
    print()
    print("Mesmo um filtro que passa aqui precisa ser confirmado no diário de sinais, nos dias que vêm.")
    print("Não é recomendação de investimento.")


if __name__ == "__main__":
    main()
