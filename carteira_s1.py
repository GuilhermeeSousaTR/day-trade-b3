#!/usr/bin/env python3
"""Teste PARA FRENTE da hipótese S1 (Momento 12-1), exatamente como em HIPOTESES.md.

Roda todo dia útil depois do fechamento (agente da noite). No ÚLTIMO pregão de cada mês:
  1. mede quanto as carteiras do mês anterior renderam (S1, referência e CDI, com custos);
  2. monta as novas carteiras: S1 (20% com maior retorno de t-12 a t-1 meses) e a
     referência (todas as elegíveis), pesos iguais.
Nos outros dias só mostra a carteira atual e o placar. Nenhuma ordem é enviada.

Arquivos: s1/carteiras.csv (composição de cada mês) e s1/placar.csv (resultado mês a mês).
Preços: Yahoo (fechamento ajustado por proventos, recalculado a cada medição). CDI: Banco Central.
Só biblioteca padrão.
"""
import csv
import datetime as dt
import importlib.util
import json
import os
import sys
import time
import urllib.error
import urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "s1")
ARQ_CART = os.path.join(PASTA, "carteiras.csv")
ARQ_PLACAR = os.path.join(PASTA, "placar.csv")
CUSTO = 0.001
FRACAO = 0.20
UA = {"User-Agent": "Mozilla/5.0 (compatible; day-trade-b3/1.0; estudo)"}
URL = "https://query1.finance.yahoo.com/v8/finance/chart/%s.SA?interval=1d&range=2y&events=div%%7Csplit"


def _sessao():
    spec = importlib.util.spec_from_file_location("b3exit", os.path.join(AQUI, "trader-exit", "exit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.session


def ultimo_pregao_do_mes(d, sessao):
    if not sessao(d):
        return False
    x = d + dt.timedelta(days=1)
    while not sessao(x):
        x += dt.timedelta(days=1)
    return x.month != d.month


def hoje_brasilia():
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()


# ------------------------------------------------------------------ dados
def lista_acoes():
    with open(os.path.join(AQUI, "trader", "universe.txt"), encoding="utf-8") as fh:
        return [ln.split("|")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def baixar_diario(sym):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(URL % sym, headers=UA), timeout=30) as r:
                res = json.loads(r.read().decode("utf-8"))["chart"]["result"][0]
            adj = res["indicators"]["adjclose"][0]["adjclose"]
            serie = {}
            for t, p in zip(res["timestamp"], adj):
                if p is not None:
                    serie[(dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t - 3 * 3600)).date()] = float(p)
            return serie
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}
            time.sleep(2 * (i + 1))
        except Exception:  # noqa: BLE001
            time.sleep(2 * (i + 1))
    return {}


def fator_cdi(d0, d1):
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
           f"&dataInicial={d0:%d/%m/%Y}&dataFinal={d1:%d/%m/%Y}")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        dados = json.loads(r.read().decode("utf-8"))
    f = 1.0
    for x in dados:
        d = dt.datetime.strptime(x["data"], "%d/%m/%Y").date()
        if d0 < d <= d1:
            f *= 1 + float(x["valor"]) / 100
    return f


def preco_em(serie, d):
    """Último preço até a data d (inclusive), se for de no máximo 5 dias antes."""
    ds = [x for x in serie if x <= d]
    if not ds:
        return None
    u = max(ds)
    return serie[u] if (d - u).days <= 7 else None


# ------------------------------------------------------------------ carteiras
def fins_de_mes(datas):
    por_mes = {}
    for d in datas:
        k = (d.year, d.month)
        por_mes[k] = max(por_mes.get(k, d), d)
    return [por_mes[k] for k in sorted(por_mes)]


def montar(series, d):
    todas = sorted({x for s in series.values() for x in s if x <= d})
    fm = fins_de_mes(todas)
    if not fm or fm[-1] != max(todas):
        fm = fm + [max(todas)]
    if len(fm) < 14:
        return [], []
    t_1, t_12 = fm[-2], fm[-13]
    janela = [x for x in todas if x > fm[-14]]
    ultimos5 = todas[-5:]
    eleg, notas = [], {}
    for sym, s in series.items():
        if sum(1 for x in janela if x in s) < 0.90 * len(janela) or not all(x in s for x in ultimos5):
            continue
        p1, p12 = preco_em(s, t_1), preco_em(s, t_12)
        if p1 is None or p12 is None:
            continue
        eleg.append(sym)
        notas[sym] = p1 / p12 - 1
    n = max(5, int(round(FRACAO * len(eleg))))
    s1 = sorted(eleg, key=lambda k: -notas[k])[:n] if eleg else []
    return s1, sorted(eleg)


def ler_csv(caminho):
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def retorno(membros, series, d0, d1):
    rs = []
    for m in membros:
        p0, p1 = preco_em(series.get(m, {}), d0), preco_em(series.get(m, {}), d1)
        rs.append(p1 / p0 - 1 if (p0 and p1) else 0.0)  # sem preço = conta como 0 (conservador)
    return sum(rs) / len(rs) if rs else 0.0


def giro(novos, antigos):
    a, b = set(novos), set(antigos)
    if not antigos:
        return 1.0
    wa, wb = 1 / len(a), 1 / len(b)
    return sum(abs((wa if k in a else 0) - (wb if k in b else 0)) for k in a | b)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", help="AAAA-MM-DD (só para testes)")
    a = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else hoje_brasilia()
    sessao = _sessao()
    os.makedirs(PASTA, exist_ok=True)
    cart = ler_csv(ARQ_CART)
    placar = ler_csv(ARQ_PLACAR)
    formacoes = sorted({r["data"] for r in cart})
    eh_fim = ultimo_pregao_do_mes(hoje, sessao)
    print("S1 Momento 12-1 — teste para frente. Hoje %s: %s." % (
        hoje.strftime("%d/%m/%Y"), "ÚLTIMO pregão do mês (dia de medir e montar carteira)" if eh_fim
        else "dia comum (só acompanhamento)"))

    if eh_fim and hoje.isoformat() not in formacoes:
        series = {}
        for sym in lista_acoes():
            s = baixar_diario(sym)
            if s:
                series[sym] = {d: p for d, p in s.items() if d <= hoje}
            time.sleep(0.3)
        if not any(hoje in s for s in series.values()):
            print("Os preços de hoje ainda não chegaram ao Yahoo; tento de novo amanhã (nada gravado).")
            return
        # 1) medir o mês anterior
        if formacoes:
            d0 = dt.date.fromisoformat(formacoes[-1])
            ant = [r for r in cart if r["data"] == formacoes[-1]]
            s1_ant = [r["acao"] for r in ant if r["carteira"] == "S1"]
            ref_ant = [r["acao"] for r in ant if r["carteira"] == "REF"]
            s1_novo, ref_novo = montar(series, hoje)
            r_s1 = retorno(s1_ant, series, d0, hoje) - CUSTO * giro(s1_novo, s1_ant)
            r_ref = retorno(ref_ant, series, d0, hoje) - CUSTO * giro(ref_novo, ref_ant)
            try:
                r_cdi = fator_cdi(d0, hoje) - 1
            except Exception:  # noqa: BLE001
                r_cdi = float("nan")
            placar.append({"inicio": d0.isoformat(), "fim": hoje.isoformat(), "s1_pct": "%.3f" % (100 * r_s1),
                           "ref_pct": "%.3f" % (100 * r_ref), "cdi_pct": "%.3f" % (100 * r_cdi),
                           "n_s1": str(len(s1_ant)), "n_ref": str(len(ref_ant))})
            with open(ARQ_PLACAR, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(placar[0]), delimiter=";")
                w.writeheader()
                w.writerows(placar)
            print("Mês medido (%s a %s): S1 %+.2f%% | referência %+.2f%% | CDI %+.2f%%"
                  % (d0.strftime("%d/%m"), hoje.strftime("%d/%m"), 100 * r_s1, 100 * r_ref, 100 * r_cdi))
        else:
            s1_novo, ref_novo = montar(series, hoje)
        # 2) montar as novas carteiras
        if not s1_novo:
            print("Sem histórico suficiente para montar a carteira (nada gravado).")
            return
        novo = not os.path.exists(ARQ_CART)
        with open(ARQ_CART, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            if novo:
                w.writerow(["data", "carteira", "acao", "peso"])
            for k in s1_novo:
                w.writerow([hoje.isoformat(), "S1", k, "%.4f" % (1 / len(s1_novo))])
            for k in ref_novo:
                w.writerow([hoje.isoformat(), "REF", k, "%.4f" % (1 / len(ref_novo))])
        cart = ler_csv(ARQ_CART)
        print("Nova carteira S1 (%d ações, pesos iguais, até o fim do próximo mês): %s"
              % (len(s1_novo), ", ".join(s1_novo)))
        print("Referência: %d ações elegíveis." % len(ref_novo))
    elif cart:
        ult = max(r["data"] for r in cart)
        s1 = [r["acao"] for r in cart if r["data"] == ult and r["carteira"] == "S1"]
        print("Carteira S1 atual (montada em %s): %s" % (dt.date.fromisoformat(ult).strftime("%d/%m/%Y"),
                                                          ", ".join(s1)))
    else:
        print("A primeira carteira será montada no último pregão do mês.")

    if placar:
        def acum(col):
            f = 1.0
            for r in placar:
                f *= 1 + float(r[col]) / 100
            return 100 * (f - 1)
        ganhou = sum(1 for r in placar if float(r["s1_pct"]) > float(r["ref_pct"]))
        print("\nPLACAR desde %s (%d meses): S1 %+.1f%% | referência %+.1f%% | CDI %+.1f%% | S1 ganhou da referência em %d mês(es)"
              % (dt.date.fromisoformat(placar[0]["inicio"]).strftime("%d/%m/%Y"), len(placar),
                 acum("s1_pct"), acum("ref_pct"), acum("cdi_pct"), ganhou))
        if len(placar) < 12:
            print("Ainda é cedo: conclusões pedem pelo menos 12 meses (o ideal são 24).")
    print("Não é recomendação de investimento.")


if __name__ == "__main__":
    main()
