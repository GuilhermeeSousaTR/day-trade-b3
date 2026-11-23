#!/usr/bin/env python3
"""Baixa barras de 5 minutos das ações da B3 no Yahoo Finance (gratuito, com atraso)
e grava em dados/ no mesmo formato que a ponte do MetaTrader grava em dados_mt5/.
Usado na nuvem (GitHub Actions), onde não há MetaTrader. Só biblioteca padrão.

  python yahoo_baixar.py                 # todas as ações de trader/universe.txt
  python yahoo_baixar.py PETR4 VALE3
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

PASTA = "dados"
URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s.SA?interval=5m&range=60d&includePrePost=false"
UA = {"User-Agent": "Mozilla/5.0 (compatible; day-trade-b3/1.0; estudo)"}


def fim_pregao(d):
    def domingo(ano, mes, n):
        x = dt.date(ano, mes, 1)
        x += dt.timedelta(days=(6 - x.weekday()) % 7)
        return x + dt.timedelta(weeks=n - 1)
    verao = domingo(d.year, 3, 2) < d <= domingo(d.year, 11, 1)
    return dt.time(16, 55) if verao else dt.time(17, 55)


def baixar(sym, tentativas=4):
    for i in range(tentativas):
        try:
            req = urllib.request.Request(URL % sym, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                doc = json.loads(r.read().decode("utf-8"))
            res = (doc.get("chart") or {}).get("result") or []
            if res and res[0].get("timestamp"):
                return doc
            return None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))  # 429 (muitas requisições) ou erro temporário
        except (urllib.error.URLError, TimeoutError, ValueError):
            time.sleep(2 * (i + 1))
    return None


def gravar_agora(ultimo_ts_utc):
    fim_barra = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=ultimo_ts_utc + 300 - 3 * 3600)
    agora = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)
    t = min(fim_barra, agora)
    t = min(t, dt.datetime.combine(t.date(), fim_pregao(t.date())) - dt.timedelta(minutes=30))
    with open(os.path.join(PASTA, "agora.txt"), "w", encoding="utf-8") as fh:
        fh.write(t.strftime("%Y-%m-%d %H:%M"))
    return t


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv:
        simbolos = [s.upper() for s in argv]
    else:
        with open("trader/universe.txt", encoding="utf-8") as fh:
            simbolos = [ln.split("|")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    os.makedirs(PASTA, exist_ok=True)
    spark, falhas, ultimo = [], [], 0
    for s in simbolos:
        doc = baixar(s)
        if not doc:
            falhas.append(s)
            continue
        with open(os.path.join(PASTA, s + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        r = doc["chart"]["result"][0]
        spark.append({"symbol": s + ".SA", "response": [r]})
        ultimo = max(ultimo, r["timestamp"][-1])
        time.sleep(0.4)
    with open(os.path.join(PASTA, "varredura_5m.json"), "w", encoding="utf-8") as fh:
        json.dump({"spark": {"result": spark, "error": None}}, fh)
    if ultimo:
        t = gravar_agora(ultimo)
        print("Horário de referência: %s (Brasília)." % t.strftime("%d/%m/%Y %H:%M"))
    print("Dados do Yahoo gravados em %s: %d de %d ações." % (PASTA, len(spark), len(simbolos)))
    if falhas:
        print("Não vieram: " + ", ".join(falhas))
    if not spark:
        sys.exit(2)


if __name__ == "__main__":
    main()
