#!/usr/bin/env python3
"""Guarda as barras de 5 min de cada pregão ENCERRADO em historico/AAAA/MM/AAAA-MM-DD.csv.gz
(um arquivo por dia, todas as ações). O Yahoo só guarda ~60 dias de barras de 5 min;
rodando todo dia, o histórico próprio cresce sem limite. Arquivos que já existem não
são reescritos. Só biblioteca padrão.

  python arquivar_dados.py              # lê dados/ (Yahoo)
  python arquivar_dados.py dados_mt5    # ou a pasta do MetaTrader
"""
import csv
import datetime as dt
import glob
import gzip
import io
import json
import os
import sys

DESTINO = "historico"


def fim_pregao(d):
    def domingo(ano, mes, n):
        x = dt.date(ano, mes, 1)
        x += dt.timedelta(days=(6 - x.weekday()) % 7)
        return x + dt.timedelta(weeks=n - 1)
    verao = domingo(d.year, 3, 2) < d <= domingo(d.year, 11, 1)
    return dt.time(16, 55) if verao else dt.time(17, 55)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    pasta = argv[0] if argv else "dados"
    agora = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)
    por_dia = {}
    for f in sorted(glob.glob(os.path.join(pasta, "*.json"))):
        sym = os.path.basename(f)[:-5]
        if sym.startswith("varredura"):
            continue
        r = json.load(open(f, encoding="utf-8"))["chart"]["result"][0]
        q = r["indicators"]["quote"][0]
        for i, t in enumerate(r.get("timestamp") or []):
            o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
            if None in (o, h, l, c):
                continue
            d = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t - 3 * 3600)).date()
            por_dia.setdefault(d, []).append((sym, t, o, h, l, c, v or 0))
    novos = []
    for d, linhas in sorted(por_dia.items()):
        encerrado = d < agora.date() or agora >= dt.datetime.combine(d, fim_pregao(d))
        if not encerrado:
            continue
        caminho = os.path.join(DESTINO, "%04d" % d.year, "%02d" % d.month, d.isoformat() + ".csv.gz")
        if os.path.exists(caminho):
            continue
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["simbolo", "ts_utc", "abertura", "maxima", "minima", "fechamento", "volume"])
        for sym, t, o, h, l, c, v in sorted(linhas):
            w.writerow([sym, t, "%.4f" % o, "%.4f" % h, "%.4f" % l, "%.4f" % c, int(v)])
        with open(caminho, "wb") as fh:  # mtime=0: arquivo idêntico se gerado de novo
            with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
                gz.write(buf.getvalue().encode("utf-8"))
        novos.append(d)
    total = len(glob.glob(os.path.join(DESTINO, "*", "*", "*.csv.gz")))
    print("Histórico: %d dia(s) novo(s) guardado(s)%s. Total no histórico: %d pregões."
          % (len(novos), (" (" + ", ".join(x.strftime("%d/%m") for x in novos[-10:])
                           + (" ..." if len(novos) > 10 else "") + ")") if novos else "", total))


if __name__ == "__main__":
    main()
