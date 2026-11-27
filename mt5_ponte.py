#!/usr/bin/env python3
"""Ponte MetaTrader 5 -> ferramentas de day trade B3 (SÓ LEITURA DE DADOS).

Lê as cotações de 5 minutos do MetaTrader 5 aberto no seu computador e grava no
mesmo formato que as ferramentas já usam (o do Yahoo). Assim a Máquina do Tempo,
a entrada e a varredura passam a usar os dados da sua corretora, sem o atraso do
Yahoo. Esta ponte NUNCA envia ordens: ela não chama nenhuma função de ordem.

    py -3.14 mt5_ponte.py teste                       # confere a conexão
    py -3.14 mt5_ponte.py baixar PETR4 VALE3 ITUB4     # grava dados_mt5\\PETR4.json etc.
    py -3.14 mt5_ponte.py baixar --lista               # todas as ações de trader\\universe.txt
    py -3.14 mt5_ponte.py historico                    # ANOS de barras de 5 min (dados_mt5_longo)

Antes: instale o MetaTrader 5, entre numa conta (de preferência DEMO) de uma
corretora que ofereça a B3 e deixe o programa aberto.
Precisa do pacote MetaTrader5 (pip install MetaTrader5), que só existe para
Windows e, por enquanto, só até o Python 3.14.
"""
import argparse
import collections
import csv
import datetime as dt
import gzip
import json
import os
import sys
import time

PASTA = "dados_mt5"
MIN5 = 300


def conectar():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("Falta o pacote MetaTrader5. No menu, a opção do MetaTrader instala sozinha "
                 "(ou rode: py -3.14 -m pip install MetaTrader5).")
    if not mt5.initialize():
        sys.exit("Não consegui falar com o MetaTrader 5 (%s). Abra o programa, entre na sua conta "
                 "e tente de novo." % (mt5.last_error(),))
    return mt5


def detectar_fuso(barras):
    """Horas a somar ao horário do servidor para chegar ao UTC.
    O pregão à vista da B3 abre às 10h de Brasília (13h UTC): a primeira barra de
    cada dia mostra em que fuso o servidor da corretora está."""
    primeiras = {}
    for b in barras:
        t = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(b["time"]))
        d = t.date()
        if d not in primeiras or t < primeiras[d]:
            primeiras[d] = t
    if not primeiras:
        return 3
    hora = collections.Counter(round(t.hour + t.minute / 60) for t in primeiras.values()).most_common(1)[0][0]
    return 13 - hora  # ex.: servidor em Brasília -> 1ª barra 10h -> soma 3h


def para_formato_yahoo(simbolo, barras, ajuste_h):
    ts, o, h, l, c, v = [], [], [], [], [], []
    for b in barras:
        ts.append(int(b["time"]) + ajuste_h * 3600)
        o.append(float(b["open"]))
        h.append(float(b["high"]))
        l.append(float(b["low"]))
        c.append(float(b["close"]))
        vol = int(b["real_volume"]) if "real_volume" in b.dtype.names and b["real_volume"] else int(b["tick_volume"])
        v.append(vol)
    agora = int(time.time())
    meta = {"symbol": simbolo + ".SA", "currency": "BRL", "dataGranularity": "5m",
            "regularMarketTime": agora, "regularMarketPrice": c[-1] if c else None,
            "fonte": "MetaTrader 5", "ajuste_fuso_horas": ajuste_h}
    return {"chart": {"result": [{"meta": meta, "timestamp": ts,
                                  "indicators": {"quote": [{"open": o, "high": h, "low": l,
                                                            "close": c, "volume": v}]}}],
                      "error": None}}


def _fim_pregao(d):
    """Fim do pregão à vista: 17h55, ou 16h55 enquanto os EUA estão em horário de verão."""
    def domingo(ano, mes, n):
        x = dt.date(ano, mes, 1)
        x += dt.timedelta(days=(6 - x.weekday()) % 7)
        return x + dt.timedelta(weeks=n - 1)
    verao = domingo(d.year, 3, 2) < d <= domingo(d.year, 11, 1)
    return dt.time(16, 55) if verao else dt.time(17, 55)


def gravar_agora(ultimo_ts_utc):
    """Grava em dados_mt5/agora.txt o horário que a varredura deve usar: agora, se o pregão
    dos dados é o de hoje e ainda está aberto; senão, o último momento do último pregão."""
    fim_barra = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=ultimo_ts_utc + MIN5 - 3 * 3600)
    agora = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)
    t = min(fim_barra, agora)
    limite = dt.datetime.combine(t.date(), _fim_pregao(t.date())) - dt.timedelta(minutes=30)  # limite de novas entradas
    t = min(t, limite)
    with open(os.path.join(PASTA, "agora.txt"), "w", encoding="utf-8") as fh:
        fh.write(t.strftime("%Y-%m-%d %H:%M"))
    return t


def ler_lista(caminho="trader/universe.txt"):
    if not os.path.exists(caminho):
        sys.exit("Não achei %s. Rode antes a varredura (opção 9) uma vez para criar a lista." % caminho)
    with open(caminho, encoding="utf-8") as fh:
        return [ln.split("|")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def cmd_teste(a):
    mt5 = conectar()
    conta = mt5.account_info()
    term = mt5.terminal_info()
    if conta is None:
        sys.exit("O MetaTrader está aberto, mas sem conta conectada. Entre numa conta e tente de novo.")
    tipo = {0: "DEMO (dinheiro de mentira)", 1: "competição", 2: "REAL"}.get(conta.trade_mode, "?")
    print("Conectado ao MetaTrader 5: %s" % (getattr(term, "name", "") or "terminal"))
    print("Corretora/servidor: %s | conta: %s" % (conta.server, tipo))
    if conta.trade_mode == 2:
        print("AVISO: conta REAL. Esta ponte só lê cotações e nunca envia ordens, mas para treinar "
              "prefira uma conta DEMO.")
    sym = a.simbolo.upper()
    if not mt5.symbol_select(sym, True):
        print("A corretora não oferece %s neste servidor (ou o código está errado)." % sym)
    else:
        r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 500)
        if r is None or len(r) == 0:
            print("Sem barras de 5 minutos para %s. Abra o gráfico dele no MetaTrader uma vez." % sym)
        else:
            aj = detectar_fuso(r)
            print("%s: %d barras de 5 min recebidas. Fuso do servidor: UTC%+d." % (sym, len(r), -aj))
    mt5.shutdown()


def cmd_baixar(a):
    mt5 = conectar()
    simbolos = ler_lista() if a.lista else [s.upper() for s in a.simbolos]
    if not simbolos:
        sys.exit("Diga quais ações, ex.: baixar PETR4 VALE3, ou use --lista.")
    os.makedirs(PASTA, exist_ok=True)
    spark, ok, falhas, ultimo = [], 0, [], 0
    for s in simbolos:
        if not mt5.symbol_select(s, True):
            falhas.append("%s (não disponível na corretora)" % s)
            continue
        r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M5, 0, a.dias * 110)
        if r is None or len(r) == 0:
            falhas.append("%s (sem barras)" % s)
            continue
        doc = para_formato_yahoo(s, r, detectar_fuso(r))
        ultimo = max(ultimo, doc["chart"]["result"][0]["timestamp"][-1])
        with open(os.path.join(PASTA, s + ".json"), "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        spark.append({"symbol": s + ".SA", "response": [doc["chart"]["result"][0]]})
        ok += 1
    with open(os.path.join(PASTA, "varredura_5m.json"), "w", encoding="utf-8") as fh:
        json.dump({"spark": {"result": spark, "error": None}}, fh)
    mt5.shutdown()
    if ultimo:
        t = gravar_agora(ultimo)
        print("Horário de referência para a varredura: %s (Brasília)." % t.strftime("%d/%m/%Y %H:%M"))
    print("Dados do MetaTrader gravados em %s: %d de %d ações." % (PASTA, ok, len(simbolos)))
    for f in falhas:
        print("  não veio: " + f)


def cmd_historico(a):
    """Baixa o máximo de barras de 5 min que a corretora oferece (anos) para a pesquisa.
    Grava dados_mt5_longo/ACAO.csv.gz com horário em UTC. Só leitura."""
    mt5 = conectar()
    simbolos = [s.upper() for s in a.simbolos] or ler_lista()
    pasta = "dados_mt5_longo"
    os.makedirs(pasta, exist_ok=True)
    term = mt5.terminal_info()
    limite = int(getattr(term, "maxbars", 0) or 100000)
    pedido = min(a.barras, limite)
    print("Limite do MetaTrader ('Máx. barras no gráfico'): %d barras de 5 min (~%.1f anos). Pedindo %d por ação."
          % (limite, limite / 95 / 250, pedido))
    tamanhos = [x for x in (pedido, 100000, 50000, 20000, 5000) if x <= pedido]
    resumo, falhas = [], []
    for n, s in enumerate(simbolos, 1):
        if not mt5.symbol_select(s, True):
            falhas.append("%s (não disponível)" % s)
            continue
        r = None
        for qtd_pedida in tamanhos:  # se o pedido grande falhar, tenta menores
            antes = -1
            for _ in range(6):  # o MetaTrader baixa do servidor aos poucos: insiste até parar de crescer
                r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M5, 0, qtd_pedida)
                qtd = 0 if r is None else len(r)
                if qtd == antes or qtd >= qtd_pedida:
                    break
                antes = qtd
                time.sleep(2)
            if r is not None and len(r) > 0:
                break
        if r is None or len(r) == 0:
            falhas.append("%s (sem barras; erro do MetaTrader: %s)" % (s, mt5.last_error()))
            continue
        aj = detectar_fuso(r)
        with gzip.open(os.path.join(pasta, s + ".csv.gz"), "wt", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["ts_utc", "open", "high", "low", "close", "volume"])
            for b in r:
                vol = int(b["real_volume"]) if "real_volume" in b.dtype.names and b["real_volume"] else int(b["tick_volume"])
                w.writerow([int(b["time"]) + aj * 3600, float(b["open"]), float(b["high"]),
                            float(b["low"]), float(b["close"]), vol])
        ini = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(r[0]["time"]) + aj * 3600)
        fim = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(r[-1]["time"]) + aj * 3600)
        resumo.append((s, len(r), ini.date(), fim.date()))
        print("  [%d/%d] %s: %d barras, de %s a %s" % (n, len(simbolos), s, len(r),
                                                     ini.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")))
    mt5.shutdown()
    print("\nHistórico gravado em %s: %d de %d ações." % (pasta, len(resumo), len(simbolos)))
    for f in falhas:
        print("  não veio: " + f)
    if resumo:
        anos = sorted((fim - ini).days / 365.25 for _, _, ini, fim in resumo)
        print("Tamanho típico do histórico: %.1f anos." % anos[len(anos) // 2])
        if anos[len(anos) // 2] < 2:
            print("Veio pouco. No MetaTrader: Ferramentas > Opções > Gráficos > 'Máx. barras no gráfico'"
                  " = Ilimitado (ou o maior número), feche e abra o programa, e rode de novo.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ponte MetaTrader 5 -> ferramentas B3 (só leitura).")
    sp = ap.add_subparsers(dest="cmd", required=True)
    t = sp.add_parser("teste")
    t.add_argument("simbolo", nargs="?", default="PETR4")
    t.set_defaults(f=cmd_teste)
    b = sp.add_parser("baixar")
    b.add_argument("simbolos", nargs="*")
    b.add_argument("--lista", action="store_true", help="usar trader/universe.txt")
    b.add_argument("--dias", type=int, default=60)
    b.set_defaults(f=cmd_baixar)
    h = sp.add_parser("historico", help="anos de barras de 5 min para a pesquisa (dados_mt5_longo)")
    h.add_argument("simbolos", nargs="*", help="vazio = todas de trader/universe.txt")
    h.add_argument("--barras", type=int, default=150000)
    h.set_defaults(f=cmd_historico)
    a = ap.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
