#!/usr/bin/env python3
"""Laboratório de swing: testa as hipóteses S1, S2 e S3 EXATAMENTE como estão em HIPOTESES.md.

  pip install yfinance pandas numpy requests matplotlib
  python pesquisa_swing.py                  # dados reais (Yahoo + CDI do Banco Central)
  python pesquisa_swing.py --demo           # dados simulados sem padrão (teste do código)
  python pesquisa_swing.py --demo-padrao    # dados simulados COM momento plantado (teste do detector)

Saídas: resultado_pesquisa_swing.txt, retornos_mensais_swing.csv, grafico_swing.png
Não é recomendação de investimento.
"""
import argparse
import math
import os

import numpy as np
import pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
INICIO_DADOS = "2014-01-01"
TREINO = ("2015-01", "2019-12")
TESTE_INICIO = "2020-01"
CUSTO = 0.001  # 0,10% sobre o valor comprado ou vendido
FRACAO = 0.20


# ------------------------------------------------------------------ dados
def lista_acoes():
    for c in (os.path.join(AQUI, "trader", "universe.txt"),
              os.path.join(AQUI, "day-trade-b3", "trader", "universe.txt")):
        if os.path.exists(c):
            with open(c, encoding="utf-8") as fh:
                return [ln.split("|")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")]
    raise SystemExit("Não achei trader/universe.txt")


def baixar_precos(tickers):
    import yfinance as yf
    df = yf.download([t + ".SA" for t in tickers], start=INICIO_DADOS, auto_adjust=True,
                     progress=False, threads=True)["Close"]
    df.columns = [c.replace(".SA", "") for c in df.columns]
    return df.dropna(how="all")


def baixar_cdi(indice):
    import requests
    partes = []
    ini = indice.min()
    while ini <= indice.max():  # a API do BC limita consultas a 10 anos
        fim = min(ini + pd.DateOffset(years=9), indice.max())
        url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
               f"&dataInicial={ini:%d/%m/%Y}&dataFinal={fim:%d/%m/%Y}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        partes.append(pd.DataFrame(r.json()))
        ini = fim + pd.Timedelta(days=1)
    s = pd.concat(partes)
    s["data"] = pd.to_datetime(s["data"], dayfirst=True)
    return (s.drop_duplicates("data").set_index("data")["valor"].astype(float) / 100)


def dados_demo(padrao, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2014-01-01", "2026-10-30")
    n = 60
    mercado = rng.normal(0.0003, 0.011, len(idx))
    precos = {}
    for i in range(n):
        beta = rng.uniform(0.6, 1.4)
        vol = rng.uniform(0.010, 0.030)
        if padrao:  # momento plantado: a tendência de cada ação muda devagar (persiste por meses)
            drift = np.zeros(len(idx))
            d = 0.0
            for k in range(len(idx)):
                if k % 21 == 0:
                    d = 0.85 * d + rng.normal(0, 0.0012)
                drift[k] = d
        else:
            drift = np.zeros(len(idx))
        ret = drift + beta * mercado + rng.normal(0, vol, len(idx))
        precos["AT%02d" % i] = 20 * np.exp(np.cumsum(ret))
    px = pd.DataFrame(precos, index=idx)
    cdi = pd.Series(0.0004, index=idx)
    return px, cdi


# ------------------------------------------------------------------ simulação
def fins_de_mes(px):
    return px.groupby(px.index.to_period("M")).apply(lambda d: d.index[-1]).tolist()


def elegiveis(px, t, i_t, datas_mes):
    if i_t < 13:
        return []
    janela = px.loc[datas_mes[i_t - 13]:t]
    ok = janela.notna().mean() >= 0.90
    ultimos = px.loc[:t].tail(5).notna().all()
    return [c for c in px.columns if ok.get(c, False) and ultimos.get(c, False)]


def escolher(regra, px, ret_d, t, i_t, datas_mes, eleg):
    if not eleg:
        return {}
    if regra in ("referencia", "S3"):
        return {c: 1 / len(eleg) for c in eleg}
    n = max(5, int(round(FRACAO * len(eleg))))
    if regra == "S1":
        p1 = px.loc[datas_mes[i_t - 1], eleg]
        p12 = px.loc[datas_mes[i_t - 12], eleg]
        nota = (p1 / p12 - 1).dropna().sort_values(ascending=False)
    elif regra == "S2":
        vol = ret_d.loc[:t, eleg].tail(126)
        vol = vol.loc[:, vol.notna().sum() >= 100].std()
        nota = vol.sort_values(ascending=True)
    else:
        raise ValueError(regra)
    escolhidas = list(nota.index[:n])
    return {c: 1 / len(escolhidas) for c in escolhidas} if escolhidas else {}


def simular(regra, px, cdi_d):
    pxf = px.ffill(limit=5)
    ret_d = px.pct_change(fill_method=None)
    datas_mes = fins_de_mes(px)
    # índice diário da carteira de referência (pesos iguais nas ações com preço no dia), para o S3
    indice = (1 + ret_d.mean(axis=1, skipna=True).fillna(0)).cumprod()
    mm200 = indice.rolling(200).mean()
    pesos_ant, linhas = {}, []
    for i_t in range(len(datas_mes) - 1):
        t, t1 = datas_mes[i_t], datas_mes[i_t + 1]
        eleg = elegiveis(px, t, i_t, datas_mes)
        if not eleg:
            continue
        w = escolher(regra, px, ret_d, t, i_t, datas_mes, eleg)
        if regra == "S3" and not (indice.loc[t] > mm200.loc[t]):
            w = {"CDI": 1.0}
        cdi_mes = float((1 + cdi_d.loc[(cdi_d.index > t) & (cdi_d.index <= t1)]).prod() - 1)
        r_ativo = {c: (pxf.loc[t1, c] / pxf.loc[t, c] - 1) if c != "CDI" else cdi_mes for c in w}
        r_ativo = {c: (0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else v)
                   for c, v in r_ativo.items()}
        giro = sum(abs(w.get(c, 0) - pesos_ant.get(c, 0)) for c in set(w) | set(pesos_ant))
        r = sum(w[c] * r_ativo[c] for c in w) - CUSTO * giro
        bruto = 1 + sum(w[c] * r_ativo[c] for c in w)
        pesos_ant = {c: w[c] * (1 + r_ativo[c]) / bruto for c in w} if bruto > 0 else {}
        linhas.append({"mes": pd.Period(t1, "M"), "ret": r, "cdi": cdi_mes, "n": len([c for c in w if c != "CDI"]),
                       "giro": giro})
    return pd.DataFrame(linhas).set_index("mes")


# ------------------------------------------------------------------ medidas
def medidas(s, ref, cdi):
    n = len(s)
    if n < 6:
        return None
    cresc = float((1 + s).prod())
    cagr = cresc ** (12 / n) - 1
    exc_cdi = s - cdi
    sharpe = exc_cdi.mean() / exc_cdi.std() * math.sqrt(12) if exc_cdi.std() > 0 else float("nan")
    acum = (1 + s).cumprod()
    dd = float((acum / acum.cummax() - 1).min())
    dif = s - ref
    t = dif.mean() / (dif.std() / math.sqrt(n)) if dif.std() > 0 else float("nan")
    cagr_ref = float((1 + ref).prod()) ** (12 / n) - 1
    return {"meses": n, "retorno_aa": 100 * cagr, "sharpe": sharpe, "maior_queda": 100 * dd,
            "acima_ref_aa": 100 * (cagr - cagr_ref), "t_vs_ref": t,
            "meses_batendo_ref": 100 * float((dif > 0).mean())}


def periodo(df, ini, fim=None):
    m = df.index >= pd.Period(ini, "M")
    if fim:
        m &= df.index <= pd.Period(fim, "M")
    return df[m]


def linha(nome, m):
    if not m:
        return "  %-26s poucos meses" % nome
    return ("  %-26s %4d meses | %+6.1f%% a.a. | Sharpe %5.2f | maior queda %6.1f%% | vs referência %+5.1f p.p. a.a. "
            "(t=%+.1f) | bate a ref. em %3.0f%% dos meses"
            % (nome, m["meses"], m["retorno_aa"], m["sharpe"], m["maior_queda"], m["acima_ref_aa"],
               m["t_vs_ref"], m["meses_batendo_ref"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--demo-padrao", action="store_true")
    a = ap.parse_args()
    if a.demo or a.demo_padrao:
        px, cdi_d = dados_demo(padrao=a.demo_padrao)
        fonte = "DADOS SIMULADOS (%s)" % ("com momento plantado" if a.demo_padrao else "sem padrão")
    else:
        px = baixar_precos(lista_acoes())
        cdi_d = baixar_cdi(px.index)
        fonte = "Yahoo Finance (fechamento ajustado) + CDI do Banco Central"
    res = {r: simular(r, px, cdi_d) for r in ("referencia", "S1", "S2", "S3")}
    ref = res["referencia"]
    nomes = {"referencia": "Referência (todas, iguais)", "S1": "S1 Momento 12-1",
             "S2": "S2 Baixa volatilidade", "S3": "S3 Filtro de tendência"}
    saida = []
    p = saida.append
    ult = ref.index.max()
    p("LABORATÓRIO DE SWING — hipóteses de HIPOTESES.md (registradas em 24/11/2026)")
    p("Fonte: %s | %d ações | custo %.2f%% por operação | rebalanceamento mensal" % (fonte, px.shape[1], 100 * CUSTO))
    p("Treino: %s a %s | Teste: %s a %s" % (TREINO[0], TREINO[1], TESTE_INICIO, ult))
    vered = {}
    for nome_p, (ini, fim) in [("TREINO", TREINO), ("TESTE", (TESTE_INICIO, None))]:
        p("")
        p(nome_p)
        rp = periodo(ref, ini, fim)
        p("  %-26s %+6.1f%% a.a." % ("CDI", 100 * (float((1 + rp["cdi"]).prod()) ** (12 / max(len(rp), 1)) - 1)))
        for r in ("referencia", "S1", "S2", "S3"):
            d = periodo(res[r], ini, fim)
            rr = periodo(ref, ini, fim).reindex(d.index)["ret"]
            m = medidas(d["ret"], rr, d["cdi"])
            vered.setdefault(r, {})[nome_p] = m
            p(linha(nomes[r], m))
    p("")
    p("VEREDITO (critério registrado: acima da referência no treino E no teste, e Sharpe maior que o dela no teste)")
    for r in ("S1", "S2", "S3"):
        tr, te = vered[r].get("TREINO"), vered[r].get("TESTE")
        rte = vered["referencia"].get("TESTE")
        if not (tr and te and rte):
            p("  %-24s dados insuficientes" % nomes[r])
            continue
        passa = tr["acima_ref_aa"] > 0 and te["acima_ref_aa"] > 0 and te["sharpe"] > rte["sharpe"]
        forte = passa and te["t_vs_ref"] > 2
        txt = ("APROVADA com evidência forte" if forte else "APROVADA, evidência fraca") if passa else "REPROVADA"
        p("  %-24s %s (treino %+.1f p.p., teste %+.1f p.p. a.a. vs referência; Sharpe teste %.2f vs %.2f)"
          % (nomes[r], txt, tr["acima_ref_aa"], te["acima_ref_aa"], te["sharpe"], rte["sharpe"]))
    p("")
    p("Como ler: 'p.p. a.a.' = pontos percentuais por ano acima (+) ou abaixo (-) da carteira com todas as ações.")
    p("t acima de 2 = diferença difícil de explicar só por sorte. Aprovada aqui ainda precisa do teste para frente.")
    p("Limitação: ações que existem hoje (viés de sobrevivência). Não é recomendação de investimento.")
    texto = "\n".join(saida)
    print(texto)
    with open("resultado_pesquisa_swing.txt", "w", encoding="utf-8") as fh:
        fh.write(texto + "\n")
    tab = pd.DataFrame({nomes[r]: res[r]["ret"] for r in res})
    tab["CDI"] = ref["cdi"]
    tab.to_csv("retornos_mensais_swing.csv", sep=";", decimal=",")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for col in tab.columns:
            s = (1 + tab[col].fillna(0)).cumprod()
            ax.plot(s.index.to_timestamp(), s.values, label=col, lw=2.2 if col.startswith("Ref") else 1.4)
        ax.axvline(pd.Timestamp(TESTE_INICIO), color="gray", ls="--", lw=1)
        ax.text(pd.Timestamp(TESTE_INICIO), ax.get_ylim()[1], "  início do teste", va="top", color="gray")
        ax.set_yscale("log")
        ax.set_ylabel("R$ 1 investido (escala log)")
        ax.set_title("Hipóteses de swing vs referência e CDI (já com custos)")
        ax.legend(loc="upper left")
        fig.tight_layout()
        fig.savefig("grafico_swing.png", dpi=130)
    except Exception as e:  # noqa: BLE001
        print("(gráfico não gerado: %s)" % e)


if __name__ == "__main__":
    main()
