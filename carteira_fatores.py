#!/usr/bin/env python3
"""Teste PARA FRENTE das hipóteses F1 (valor) e F2 (qualidade), aprovadas com evidência fraca em
HIPOTESES_FATORES.md. Mesmas regras da pesquisa, aplicadas mês a mês daqui para a frente.

Roda todo dia útil depois do fechamento (agente da noite). No ÚLTIMO pregão de cada mês:
  1. baixa os balanços recentes da CVM, preços e CDI (baixar_fatores.py --desde ano-2);
  2. mede quanto as carteiras do mês anterior renderam (F1, F2, referência e CDI, com custos);
  3. monta as novas carteiras F1, F2 e a referência (todas as elegíveis), pesos iguais.
Nos outros dias só mostra as carteiras atuais e o placar. Nenhuma ordem é enviada.

Arquivos: fatores/carteiras.csv e fatores/placar.csv. Não é recomendação de investimento.
"""
import csv
import datetime as dt
import os
import subprocess
import sys

import carteira_s1 as cs1

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "fatores")
ARQ_CART = os.path.join(PASTA, "carteiras.csv")
ARQ_PLACAR = os.path.join(PASTA, "placar.csv")
REGRAS = ("F1", "F2")


def preparar_bibliotecas():
    try:
        import pandas  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pandas", "numpy"], check=False)


def montar(hoje, pasta):
    import pesquisa_fatores as pf
    sw = pf.sw
    px, fc, desd = pf.carregar_precos(pasta)
    px = px[px.index.date <= hoje]
    if px.empty or px.index[-1].date() != hoje:
        return None, None
    import csv as _csv
    with open(os.path.join(pasta, "mapa_tickers.csv"), encoding="utf-8") as fh:
        mapa = {r["ticker"]: r["cnpj"] for r in _csv.DictReader(fh, delimiter=";")}
    desd_cnpj = {}
    for sym, c in mapa.items():
        if sym in desd and c not in desd_cnpj:
            desd_cnpj[c] = desd[sym]
    regs = pf.carregar_balancos(pasta, desd_cnpj)
    datas_mes = sw.fins_de_mes(px)
    t = datas_mes[-1]
    eleg = sw.elegiveis(px, t, len(datas_mes) - 1, datas_mes)
    notas = pf.montar_notas(px, fc, desd, regs, mapa, [t])
    novas = {"REF": sorted(eleg)}
    for r in REGRAS:
        novas[r] = sorted(pf.escolher(r, notas, eleg))
    series = {c: {d.date(): float(v) for d, v in px[c].dropna().items()} for c in px.columns}
    return novas, series


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", help="AAAA-MM-DD (só para testes)")
    ap.add_argument("--sem-baixar", action="store_true", help="usa dados_fatores já baixado (testes)")
    ap.add_argument("--forcar", action="store_true", help="trata hoje como fim de mês (testes)")
    a = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else cs1.hoje_brasilia()
    eh_fim = a.forcar or cs1.ultimo_pregao_do_mes(hoje, cs1._sessao())
    os.makedirs(PASTA, exist_ok=True)
    cart = cs1.ler_csv(ARQ_CART)
    placar = cs1.ler_csv(ARQ_PLACAR)
    formacoes = sorted({r["data"] for r in cart})
    print("F1 Valor e F2 Qualidade — teste para frente. Hoje %s: %s." % (
        hoje.strftime("%d/%m/%Y"), "ÚLTIMO pregão do mês (dia de medir e montar carteira)" if eh_fim
        else "dia comum (só acompanhamento)"))

    if eh_fim and hoje.isoformat() not in formacoes:
        preparar_bibliotecas()
        pasta = os.path.join(AQUI, "dados_fatores")
        if not a.sem_baixar:
            print("Baixando balanços recentes da CVM, preços e CDI...")
            subprocess.run([sys.executable, os.path.join(AQUI, "baixar_fatores.py"), "--desde", str(hoje.year - 2)],
                           check=False, stdout=subprocess.DEVNULL)
        novas, series = montar(hoje, pasta)
        if novas is None:
            print("Os preços de hoje ainda não chegaram; tento de novo amanhã (nada gravado).")
            return
        if formacoes:
            d0 = dt.date.fromisoformat(formacoes[-1])
            linha = {"inicio": d0.isoformat(), "fim": hoje.isoformat()}
            for r in ("F1", "F2", "REF"):
                ant = [x["acao"] for x in cart if x["data"] == formacoes[-1] and x["carteira"] == r]
                ret = cs1.retorno(ant, series, d0, hoje) - cs1.CUSTO * cs1.giro(novas[r], ant)
                linha[r.lower() + "_pct"] = "%.3f" % (100 * ret)
            try:
                linha["cdi_pct"] = "%.3f" % (100 * (cs1.fator_cdi(d0, hoje) - 1))
            except Exception:  # noqa: BLE001
                linha["cdi_pct"] = "nan"
            placar.append(linha)
            with open(ARQ_PLACAR, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(placar[0]), delimiter=";")
                w.writeheader()
                w.writerows(placar)
            print("Mês medido (%s a %s): F1 %s%% | F2 %s%% | referência %s%% | CDI %s%%"
                  % (d0.strftime("%d/%m"), hoje.strftime("%d/%m"), linha["f1_pct"], linha["f2_pct"],
                     linha["ref_pct"], linha["cdi_pct"]))
        if not novas["F1"] and not novas["F2"]:
            print("Sem dados suficientes para montar as carteiras (nada gravado).")
            return
        novo = not os.path.exists(ARQ_CART)
        with open(ARQ_CART, "a", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            if novo:
                w.writerow(["data", "carteira", "acao", "peso"])
            for r, membros in novas.items():
                for k in membros:
                    w.writerow([hoje.isoformat(), r, k, "%.4f" % (1 / len(membros))])
        print("Nova carteira F1 Valor (%d): %s" % (len(novas["F1"]), ", ".join(novas["F1"])))
        print("Nova carteira F2 Qualidade (%d): %s" % (len(novas["F2"]), ", ".join(novas["F2"])))
        print("Referência: %d ações elegíveis." % len(novas["REF"]))
    elif cart:
        ult = max(r["data"] for r in cart)
        for r in REGRAS:
            m = [x["acao"] for x in cart if x["data"] == ult and x["carteira"] == r]
            print("Carteira %s atual (montada em %s): %s" % (r, dt.date.fromisoformat(ult).strftime("%d/%m/%Y"),
                                                             ", ".join(m)))
    else:
        print("As primeiras carteiras serão montadas no último pregão do mês.")

    if placar:
        def acum(col):
            f = 1.0
            for x in placar:
                f *= 1 + float(x[col]) / 100
            return 100 * (f - 1)
        print("\nPLACAR desde %s (%d meses): F1 %+.1f%% | F2 %+.1f%% | referência %+.1f%% | CDI %+.1f%%"
              % (dt.date.fromisoformat(placar[0]["inicio"]).strftime("%d/%m/%Y"), len(placar),
                 acum("f1_pct"), acum("f2_pct"), acum("ref_pct"), acum("cdi_pct")))
        if len(placar) < 12:
            print("Ainda é cedo: conclusões pedem pelo menos 12 meses (o ideal são 24).")
    print("Não é recomendação de investimento.")


if __name__ == "__main__":
    main()
