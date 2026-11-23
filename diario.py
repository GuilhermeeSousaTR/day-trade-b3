#!/usr/bin/env python3
"""Diário de sinais: teste PARA FRENTE do rompimento da faixa de abertura.

A cada pregão encerrado desde INICIO, registra em diario_sinais.csv todos os sinais
da regra (com stop, alvo, como terminou e resultado já com custo) e mostra o placar
acumulado. Esses dias nunca foram usados em nenhum teste: é a prova mais honesta.
Só lê dados; não envia ordens.

  py -3.14 mt5_ponte.py baixar --lista     (antes, para atualizar os dados)
  python diario.py
"""
import csv
import datetime as dt
import os

from backtest_orb import fim_pregao, linha, resumo
from testar_filtros import FILTROS, coletar

INICIO = dt.date(2026, 11, 23)  # 1º pregão depois de todos os testes feitos com os dados históricos
ARQ = "diario_sinais.csv"
CAMPOS = ["data", "acao", "hora_entrada", "entrada", "stop", "alvo", "saida", "como_terminou",
          "resultado_pct"] + FILTROS


def agora_brasilia():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="dados_mt5", help="dados_mt5 (MetaTrader) ou dados (Yahoo, na nuvem)")
    a = ap.parse_args(argv)
    agora = agora_brasilia()
    ja = set()
    if os.path.exists(ARQ):
        with open(ARQ, encoding="utf-8") as fh:
            ja = {r["data"] for r in csv.DictReader(fh, delimiter=";")}
    ops = coletar(a.pasta, 1.0, 0.001)
    encerrado = lambda d: d < agora.date() or agora >= dt.datetime.combine(d, fim_pregao(d))
    novos = sorted([o for o in ops if o["dia"] >= INICIO and encerrado(o["dia"])
                    and o["dia"].isoformat() not in ja], key=lambda o: (o["dia"], o["hora"]))
    novo_arq = not os.path.exists(ARQ)
    with open(ARQ, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo_arq:
            w.writerow(CAMPOS)
        for o in novos:
            w.writerow([o["dia"].isoformat(), o["sym"], o["hora"].strftime("%H:%M"),
                        ("%.2f" % o["entrada"]).replace(".", ","), ("%.2f" % o["stop"]).replace(".", ","),
                        ("%.2f" % o["alvo"]).replace(".", ","), ("%.2f" % o["saida"]).replace(".", ","),
                        o["como"], ("%.3f" % (100 * o["ret"])).replace(".", ",")]
                       + ["sim" if o[f] else "nao" for f in FILTROS])
    dias_novos = sorted({o["dia"] for o in novos})
    print("Diário de sinais (início em %s). Registrados agora: %d sinais de %d pregão(ões)%s."
          % (INICIO.strftime("%d/%m/%Y"), len(novos), len(dias_novos),
             (": " + ", ".join(d.strftime("%d/%m") for d in dias_novos)) if dias_novos else ""))
    todos = []  # placar vem da planilha (permanente), não dos dados baixados (só ~2 meses)
    with open(ARQ, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            o = {"dia": dt.date.fromisoformat(r["data"]), "ret": float(r["resultado_pct"].replace(",", ".")) / 100}
            o.update({f: r[f] == "sim" for f in FILTROS})
            todos.append(o)
    hoje = [o for o in ops if o["dia"] == agora.date() and not encerrado(o["dia"])]
    if hoje:
        print("\nHoje, pregão em andamento (%d sinais até agora; o resultado entra no diário depois do fechamento):"
              % len(hoje))
        for o in sorted(hoje, key=lambda o: o["hora"])[:15]:
            print("  %s  %-7s entrada %.2f  stop %.2f  alvo %.2f" % (o["hora"].strftime("%H:%M"), o["sym"],
                                                                     o["entrada"], o["stop"], o["alvo"]))
    if not todos:
        print("\nAinda não há pregão encerrado desde o início do diário. Rode de novo depois das 18h de um dia útil.")
        return
    print("\nPLACAR ACUMULADO desde %s:" % INICIO.strftime("%d/%m/%Y"))
    print(linha("regra sem filtro", resumo(todos)))
    for f in FILTROS:
        print(linha("só com " + f, resumo([o for o in todos if o[f]])))
    n_dias = len({o["dia"] for o in todos})
    if n_dias < 40:
        print("\nSó %d pregão(ões) no diário: ainda é cedo. Conclusões firmes pedem uns 40 pregões (2 meses)." % n_dias)
    print("Planilha completa: %s (abre no Excel ou no Power BI). Não é recomendação de investimento."
          % os.path.abspath(ARQ))


if __name__ == "__main__":
    main()
