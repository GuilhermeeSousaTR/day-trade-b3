#!/usr/bin/env python3
"""Converte o histórico guardado (historico/*.csv.gz) de volta para o formato que os
testes usam, numa pasta (padrão dados_hist/). Assim dá para testar ideias em TODO o
histórico acumulado, não só nos ~60 dias que o Yahoo oferece.

  python historico_para_dados.py
  python backtest_orb.py --pasta dados_hist
  python testar_filtros.py --pasta dados_hist
"""
import collections
import csv
import glob
import gzip
import json
import os
import sys


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    saida = argv[0] if argv else "dados_hist"
    series = collections.defaultdict(list)
    arquivos = sorted(glob.glob(os.path.join("historico", "*", "*", "*.csv.gz")))
    for f in arquivos:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                series[r["simbolo"]].append((int(r["ts_utc"]), float(r["abertura"]), float(r["maxima"]),
                                             float(r["minima"]), float(r["fechamento"]), int(r["volume"])))
    os.makedirs(saida, exist_ok=True)
    for sym, barras in series.items():
        barras.sort()
        t, o, h, l, c, v = (list(x) for x in zip(*barras))
        doc = {"chart": {"result": [{"meta": {"symbol": sym + ".SA", "currency": "BRL", "fonte": "historico"},
                                     "timestamp": t,
                                     "indicators": {"quote": [{"open": o, "high": h, "low": l,
                                                               "close": c, "volume": v}]}}],
                         "error": None}}
        with open(os.path.join(saida, sym + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    print("Histórico convertido: %d pregões, %d ações -> pasta %s" % (len(arquivos), len(series), saida))


if __name__ == "__main__":
    main()
