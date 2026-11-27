#!/usr/bin/env python3
"""Pesquisa de fatores: testa F1 (valor), F2 (qualidade) e F3 (valor + qualidade) EXATAMENTE como estão
em HIPOTESES_FATORES.md, com balanços da CVM usados só a partir da data de entrega.

  python baixar_fatores.py              (antes: baixa balanços, preços e CDI para dados_fatores)
  python pesquisa_fatores.py            (dados reais)
  python pesquisa_fatores.py --demo     (dados falsos SEM efeito: as três devem ser reprovadas)
  python pesquisa_fatores.py --demo-padrao  (dados falsos COM efeito de valor: F1 deve passar)

Saídas: resultado_fatores.txt, retornos_mensais_fatores.csv, fundamentos_mensais.csv
Usa o mesmo simulador, custos e referência da pesquisa de swing (pesquisa_swing.py).
Não é recomendação de investimento.
"""
import argparse
import collections
import csv
import datetime as dt
import glob
import gzip
import json
import math
import os
import re

import numpy as np
import pandas as pd

import pesquisa_swing as sw

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "dados_fatores")
TREINO = ("2013-01", "2019-12")
TESTE_INICIO = "2020-01"
T_FORTE = 2.64          # 5% corrigido para 6 hipóteses mensais (Bonferroni)
MESES_VELHO = 7
REGRAS = ("F1", "F2", "F3")
NOMES = {"referencia": "Referência (todas, iguais)", "F1": "F1 Valor (lucro/preço)",
         "F2": "F2 Qualidade (ROE)", "F3": "F3 Valor + qualidade"}


# ------------------------------------------------------------------ leitura dos balanços da CVM
def _num(x):
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def _data(x):
    try:
        return dt.date.fromisoformat(str(x).strip()[:10])
    except ValueError:
        return None


def _ler(caminho):
    with gzip.open(caminho, "rt", encoding="utf-8", newline="") as fh:
        it = csv.reader(fh, delimiter=";")
        cab = [c.strip().upper() for c in next(it)]
        for r in it:
            yield dict(zip(cab, r))


def _escala(r):
    return 1000.0 if str(r.get("ESCALA_MOEDA", "")).strip().upper().startswith("MIL") else 1.0


def _ultimo(r):
    return not str(r.get("ORDEM_EXERC", "")).strip().upper().startswith("PEN")


NIVEL1 = re.compile(r"^\d\.\d{2}$")


def lucro_do_bloco(linhas):
    """Lucro líquido de um bloco da DRE (um documento, um período): atribuído aos controladores se houver."""
    cand = []
    for r in linhas:
        cd, ds = r["CD_CONTA"].strip(), r["DS_CONTA"].strip().lower()
        if not NIVEL1.match(cd) or not cd.startswith("3.") or cd == "3.99":
            continue
        if not ("lucro" in ds or "prejuízo" in ds or "resultado líquido" in ds):
            continue
        if any(x in ds for x in ("por ação", "antes", "bruto", "operacional", "tributo", "financeir")):
            continue
        cand.append(r)
    if not cand:
        return None
    final = max(cand, key=lambda r: [int(x) for x in r["CD_CONTA"].split(".")])
    cd = final["CD_CONTA"].strip()
    for r in linhas:
        ds = r["DS_CONTA"].strip().lower()
        if r["CD_CONTA"].strip().startswith(cd + ".") and "controlador" in ds and "não" not in ds and "nao" not in ds:
            v = _num(r["VL_CONTA"])
            if v is not None:
                return v * _escala(r)
    v = _num(final["VL_CONTA"])
    return None if v is None else v * _escala(final)


def pl_do_bloco(linhas):
    """Patrimônio líquido atribuído aos controladores (total menos não controladores)."""
    tot = None
    for r in linhas:
        cd, ds = r["CD_CONTA"].strip(), r["DS_CONTA"].strip().lower()
        if NIVEL1.match(cd) and cd.startswith("2.") and "patrim" in ds and "quido" in ds:
            tot = r
    if tot is None:
        return None
    v = _num(tot["VL_CONTA"])
    if v is None:
        return None
    v *= _escala(tot)
    cd = tot["CD_CONTA"].strip()
    for r in linhas:
        ds = r["DS_CONTA"].strip().lower()
        if r["CD_CONTA"].strip().startswith(cd + ".") and ("não controlador" in ds or "nao controlador" in ds
                                                           or "minorit" in ds):
            x = _num(r["VL_CONTA"])
            if x is not None:
                v -= x * _escala(r)
            break
    return v


def eps_do_bloco(linhas):
    """Lucro básico por ação (primeira classe com valor), como informado (escala não confiável)."""
    for r in sorted(linhas, key=lambda r: r["CD_CONTA"]):
        if r["CD_CONTA"].strip().startswith("3.99.01.") and _num(r["VL_CONTA"]):
            return _num(r["VL_CONTA"])
    return None


def carregar_balancos(pasta, desd_cnpj=None):
    """Devolve {cnpj: [registro, ...]} com disponivel_em, dt_refer, ll12, pl, acoes.
    Ações: quantidade oficial (composição do capital, existe a partir de 2020). Antes disso, lucro do
    período ÷ lucro por ação, com a escala (x1, x1000, ÷1000) escolhida pela mais próxima da quantidade
    oficial mais antiga ajustada por desdobramentos; se nem assim ficar a menos de 2x, usa essa âncora."""
    desd_cnpj = desd_cnpj or {}
    cvm = os.path.join(pasta, "cvm")
    receb = {}
    for f in glob.glob(os.path.join(cvm, "*_indice_*.csv.gz")):
        tipo = os.path.basename(f).split("_")[0]
        for r in _ler(f):
            k = (tipo, r["CNPJ_CIA"].strip(), _data(r["DT_REFER"]), r.get("VERSAO", "1").strip())
            d = _data(r.get("DT_RECEB", ""))
            if d and k[2]:
                receb[k] = min(d, receb.get(k, d))

    def blocos(parte):
        out = collections.defaultdict(list)
        for f in glob.glob(os.path.join(cvm, "*_%s_*.csv.gz" % parte)):
            tipo = os.path.basename(f).split("_")[0]
            for r in _ler(f):
                k = (tipo, r["CNPJ_CIA"].strip(), _data(r["DT_REFER"]), r.get("VERSAO", "1").strip())
                out[k].append(r)
        return out

    dre_con, dre_ind = blocos("DRE_con"), blocos("DRE_ind")
    bpp_con, bpp_ind = blocos("BPP_con"), blocos("BPP_ind")
    acoes = {}
    for f in glob.glob(os.path.join(cvm, "*_composicao_capital_*.csv.gz")):
        tipo = os.path.basename(f).split("_")[0]
        for r in _ler(f):
            k = (tipo, r["CNPJ_CIA"].strip(), _data(r["DT_REFER"]), r.get("VERSAO", "1").strip())
            tot = _num(r.get("QT_ACAO_TOTAL_CAP_INTEGR", ""))
            tes = _num(r.get("QT_ACAO_TOTAL_TESOURO", "")) or 0.0
            if tot:
                acoes[k] = tot - tes

    def grupos(linhas):
        g = collections.defaultdict(list)
        for r in linhas:
            g[(_ultimo(r), _data(r.get("DT_INI_EXERC", "")), _data(r.get("DT_FIM_EXERC", "")))].append(r)
        return g

    def periodos(linhas):
        """{(ultimo?, dt_ini, dt_fim): lucro}"""
        return {k: lucro_do_bloco(v) for k, v in grupos(linhas).items()}

    # âncora: quantidade oficial mais antiga de cada empresa
    ancora = {}
    for (tipo, cnpj, refer, _), q in acoes.items():
        if q and q > 0 and (cnpj not in ancora or refer < ancora[cnpj][0]):
            ancora[cnpj] = (refer, q)

    def acoes_estimadas(cnpj, refer, linhas):
        """Antes de 2020: lucro ÷ lucro por ação do mesmo período; sem isso, a quantidade oficial mais
        antiga ajustada por desdobramentos. A escala (milhares ou unidades) é resolvida em montar_notas."""
        for (u, i, fim), bl in grupos(linhas).items():
            if u and fim == refer:
                ll, eps = lucro_do_bloco(bl), eps_do_bloco(bl)
                if ll and eps:
                    return abs(ll / eps), "lucro por ação"
        if cnpj in ancora:
            r0, q0 = ancora[cnpj]
            f = 1.0
            for d, razao in desd_cnpj.get(cnpj, []):
                if refer < d <= r0:
                    f *= razao
            return q0 / f, "âncora 2020"
        return None, "sem"

    # lucro anual (DFP) por (cnpj, fim do exercício): lista de (recebido_em, valor)
    anual = collections.defaultdict(list)
    for k, rec in receb.items():
        if k[0] != "DFP":
            continue
        linhas = dre_con.get(k) or dre_ind.get(k) or []
        for (ult, ini, fim), v in periodos(linhas).items():
            if ult and v is not None and ini and fim and (fim - ini).days > 300:
                anual[(k[1], fim)].append((rec, v))

    def anual_em(cnpj, fim, ate):
        ok = [(r, v) for r, v in anual.get((cnpj, fim), []) if r <= ate]
        return max(ok)[1] if ok else None

    regs = collections.defaultdict(list)
    for k, rec in receb.items():
        tipo, cnpj, refer, _ = k
        linhas = dre_con.get(k) or dre_ind.get(k) or []
        per = periodos(linhas)
        ll12 = None
        if tipo == "DFP":
            vals = [v for (u, i, f), v in per.items() if u and i and f and (f - i).days > 300 and v is not None]
            ll12 = vals[0] if vals else None
        else:
            ytd = [(i, f, v) for (u, i, f), v in per.items() if u and i and f == refer and v is not None]
            if ytd:
                ini, fim, v_ytd = min(ytd)  # o período que começa mais cedo = acumulado do ano
                if (fim - ini).days > 300:
                    ll12 = v_ytd
                else:
                    ant = [v for (u, i, f), v in per.items() if not u and i and f and v is not None
                           and abs((i - ini).days - (-365)) <= 3 and abs((f - fim).days - (-365)) <= 3]
                    a = anual_em(cnpj, ini - dt.timedelta(days=1), rec)
                    if ant and a is not None:
                        ll12 = a + v_ytd - ant[0]
        bl = [r for r in (bpp_con.get(k) or bpp_ind.get(k) or []) if _ultimo(r)]
        if not linhas and not bl:
            continue  # versão que não está nos arquivos (a CVM guarda só a mais recente)
        q, fonte_q = (acoes.get(k), "oficial") if acoes.get(k) else acoes_estimadas(cnpj, refer, linhas)
        regs[cnpj].append({"disponivel_em": rec, "dt_refer": refer, "ll12": ll12,
                           "pl": pl_do_bloco(bl) if bl else None, "acoes": q, "fonte_acoes": fonte_q})
    for c in regs:
        regs[c].sort(key=lambda x: (x["disponivel_em"], x["dt_refer"]))
    return regs


# ------------------------------------------------------------------ preços
def carregar_precos(pasta):
    """adjclose (para retornos), close (só ajustado por desdobramento) e desdobramentos por ação."""
    adj, fech, desd = {}, {}, {}
    for f in sorted(glob.glob(os.path.join(pasta, "precos", "*.json.gz"))):
        sym = os.path.basename(f).split(".")[0]
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            res = json.load(fh)
        ts = res.get("timestamp") or []
        q = res["indicators"]["quote"][0]
        a = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
        idx = pd.to_datetime([dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t - 3 * 3600) for t in ts]).normalize()
        adj[sym] = pd.Series(a, index=idx, dtype=float)
        fech[sym] = pd.Series(q["close"], index=idx, dtype=float)
        desd[sym] = sorted(((dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(e["date"]) - 3 * 3600)).date(),
                            float(e["numerator"]) / float(e["denominator"]))
                           for e in (res.get("events") or {}).get("splits", {}).values()
                           if e.get("denominator"))
    px = pd.DataFrame(adj).sort_index()
    px = px[~px.index.duplicated(keep="last")]
    fc = pd.DataFrame(fech).sort_index()
    fc = fc[~fc.index.duplicated(keep="last")]
    return px, fc, desd


def carregar_cdi(pasta, indice):
    s = pd.read_csv(os.path.join(pasta, "cdi.csv"), sep=";", parse_dates=["data"]).set_index("data")
    return (s["cdi_pct_ao_dia"].astype(float) / 100).reindex(indice).fillna(0.0)


def fator_desdobramento(lista, depois_de):
    f = 1.0
    for d, r in lista:
        if d > depois_de:
            f *= r
    return f


# ------------------------------------------------------------------ notas de cada mês
def montar_notas(px, fc, desd, regs, mapa, datas_mes):
    """DataFrame (data, ação) com ll12, pl, valor de mercado, EY e ROE, como estavam disponíveis no dia."""
    linhas = []
    for t in datas_mes:
        td = t.date()
        for sym in px.columns:
            cnpj = mapa.get(sym)
            if not cnpj or cnpj not in regs:
                continue
            disp = [r for r in regs[cnpj] if r["disponivel_em"] <= td and r["ll12"] is not None]
            if not disp:
                continue
            # o balanço mais recente já entregue (por data de referência)
            ult_ref = max(r["dt_refer"] for r in disp)
            if (td - ult_ref).days > MESES_VELHO * 31:
                continue
            r = [x for x in disp if x["dt_refer"] == ult_ref][-1]
            acoes_reg = [x for x in regs[cnpj] if x["disponivel_em"] <= td and x["acoes"]]
            if not acoes_reg:
                continue
            ra = max(acoes_reg, key=lambda x: (x["dt_refer"], x["disponivel_em"]))
            preco = fc.at[t, sym] if t in fc.index else np.nan
            if not (preco == preco) or preco <= 0:
                continue
            vm = preco * ra["acoes"] * fator_desdobramento(desd.get(sym, []), ra["dt_refer"])
            # a CVM mistura quantidades em unidades e em milhares (e lucro por ação idem), sem avisar:
            # escolhe a escala (x1000, x1, ÷1000) que deixa preço/patrimônio perto de 2 (ou P/L perto de 10)
            if r["pl"] and r["pl"] > 0:
                base, alvo = r["pl"], math.log10(2)
            else:
                base, alvo = abs(r["ll12"]) or None, 1.0
            if not base:
                continue
            vm = min((vm * e for e in (1000.0, 1.0, 0.001)), key=lambda v: abs(math.log10(v / base) - alvo))
            linhas.append({"data": t, "acao": sym, "dt_refer": ult_ref, "ll12": r["ll12"], "pl": r["pl"],
                           "valor_mercado": vm, "ey": r["ll12"] / vm if vm > 0 else np.nan,
                           "roe": (r["ll12"] / r["pl"]) if (r["pl"] and r["pl"] > 0) else np.nan})
    return pd.DataFrame(linhas)


def escolher(regra, notas_t, eleg):
    if notas_t is None or notas_t.empty:
        return {}
    d = notas_t[notas_t["acao"].isin(eleg)].set_index("acao")
    if regra == "F1":
        d = d[d["ll12"] > 0]
        nota = d["ey"].sort_values(ascending=False)
    elif regra == "F2":
        d = d[(d["ll12"] > 0) & (d["pl"] > 0)]
        nota = d["roe"].sort_values(ascending=False)
    elif regra == "F3":
        d = d[(d["ll12"] > 0) & (d["pl"] > 0)]
        soma = d["ey"].rank(ascending=False) + d["roe"].rank(ascending=False)
        nota = soma.sort_values(ascending=True)
    else:
        raise ValueError(regra)
    nota = nota.dropna()
    if len(nota) < 5:
        return {}
    # 20% das elegíveis por preço (a mesma régua da S1), mínimo 5
    n = max(5, int(round(sw.FRACAO * len(eleg))))
    esc = list(nota.index[:n])
    return {c: 1 / len(esc) for c in esc}


def simular(regra, px, cdi_d, notas):
    pxf = px.ffill(limit=5)
    datas_mes = sw.fins_de_mes(px)
    por_data = {t: g for t, g in notas.groupby("data")} if not notas.empty else {}
    pesos_ant, linhas = {}, []
    for i_t in range(len(datas_mes) - 1):
        t, t1 = datas_mes[i_t], datas_mes[i_t + 1]
        eleg = sw.elegiveis(px, t, i_t, datas_mes)
        if not eleg:
            continue
        if regra == "referencia":
            w = {c: 1 / len(eleg) for c in eleg}
        else:
            w = escolher(regra, por_data.get(t), eleg)
            if not w:
                continue
        cdi_mes = float((1 + cdi_d.loc[(cdi_d.index > t) & (cdi_d.index <= t1)]).prod() - 1)
        r_at = {}
        for c in w:
            v = pxf.at[t1, c] / pxf.at[t, c] - 1
            r_at[c] = 0.0 if (v is None or (isinstance(v, float) and math.isnan(v))) else v
        giro = sum(abs(w.get(c, 0) - pesos_ant.get(c, 0)) for c in set(w) | set(pesos_ant))
        r = sum(w[c] * r_at[c] for c in w) - sw.CUSTO * giro
        bruto = 1 + sum(w[c] * r_at[c] for c in w)
        pesos_ant = {c: w[c] * (1 + r_at[c]) / bruto for c in w} if bruto > 0 else {}
        linhas.append({"mes": pd.Period(t1, "M"), "ret": r, "cdi": cdi_mes, "n": len(w), "giro": giro,
                       "carteira": " ".join(sorted(w))})
    return pd.DataFrame(linhas).set_index("mes")


# ------------------------------------------------------------------ dados falsos (validação)
def dados_falsos(padrao, seed=9):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-03", "2026-10-30")
    n = 60
    mercado = rng.normal(0.0003, 0.011, len(idx))
    adj, regs, mapa = {}, {}, {}
    for i in range(n):
        sym, cnpj = "AT%02d" % i, "C%02d" % i
        ey_base = rng.uniform(0.02, 0.20)               # lucro/preço "verdadeiro" da empresa
        alfa = (ey_base - 0.11) * 0.003 if padrao else 0.0  # com padrão: baratas rendem mais
        ret = alfa + rng.uniform(0.6, 1.4) * mercado + rng.normal(0, rng.uniform(0.012, 0.03), len(idx))
        p = 20 * np.exp(np.cumsum(ret))
        adj[sym] = pd.Series(p, index=idx)
        acoes = 1e8
        mapa[sym] = cnpj
        regs[cnpj] = []
        for d in pd.date_range("2011-03-31", "2026-09-30", freq="QE"):
            preco = float(adj[sym].asof(d))
            ey = max(0.001, ey_base * rng.lognormal(0, 0.25))
            regs[cnpj].append({"disponivel_em": (d + pd.Timedelta(days=45)).date(), "dt_refer": d.date(),
                               "ll12": ey * preco * acoes, "pl": ey * preco * acoes / rng.uniform(0.08, 0.25),
                               "acoes": acoes})
    px = pd.DataFrame(adj)
    return px, px.copy(), {}, regs, mapa, pd.Series(0.0004, index=idx)


# ------------------------------------------------------------------ principal
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default=PASTA)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--demo-padrao", action="store_true")
    a = ap.parse_args(argv)
    if a.demo or a.demo_padrao:
        px, fc, desd, regs, mapa, cdi_d = dados_falsos(a.demo_padrao)
        fonte = "DADOS FALSOS (%s)" % ("com efeito de valor plantado" if a.demo_padrao else "sem efeito")
    else:
        px, fc, desd = carregar_precos(a.pasta)
        cdi_d = carregar_cdi(a.pasta, px.index)
        with open(os.path.join(a.pasta, "mapa_tickers.csv"), encoding="utf-8") as fh:
            mapa = {r["ticker"]: r["cnpj"] for r in csv.DictReader(fh, delimiter=";")}
        desd_cnpj = {}
        for sym, c in mapa.items():
            if sym in desd and c not in desd_cnpj:
                desd_cnpj[c] = desd[sym]
        regs = carregar_balancos(a.pasta, desd_cnpj)
        fonte = "CVM (balanços) + Yahoo (preços) + Banco Central (CDI)"
    datas_mes = sw.fins_de_mes(px)
    notas = montar_notas(px, fc, desd, regs, mapa, datas_mes)
    res = {r: simular(r, px, cdi_d, notas) for r in ("referencia",) + REGRAS}
    ref = res["referencia"]
    saida = []
    p = saida.append
    p("PESQUISA DE FATORES — hipóteses de HIPOTESES_FATORES.md (registradas em 24/11/2026)")
    p("Fonte: %s | %d ações com preço | %d com balanço | custo %.2f%% sobre o giro | rebalanceamento mensal"
      % (fonte, px.shape[1], notas["acao"].nunique() if not notas.empty else 0, 100 * sw.CUSTO))
    p("Treino: %s a %s | Teste: %s a %s" % (TREINO[0], TREINO[1], TESTE_INICIO, ref.index.max()))
    if not notas.empty:
        cob = notas.groupby("data")["acao"].nunique()
        p("Ações com balanço utilizável por mês: mínimo %d, mediana %d, máximo %d"
          % (cob.min(), cob.median(), cob.max()))
    vered = {}
    for nome_p, (ini, fim) in [("TREINO", TREINO), ("TESTE", (TESTE_INICIO, None))]:
        p("")
        p(nome_p)
        rp = sw.periodo(ref, ini, fim)
        p("  %-26s %+6.1f%% a.a." % ("CDI", 100 * (float((1 + rp["cdi"]).prod()) ** (12 / max(len(rp), 1)) - 1)))
        for r in ("referencia",) + REGRAS:
            d = sw.periodo(res[r], ini, fim) if not res[r].empty else res[r]
            if d.empty:
                p("  %-26s sem meses" % NOMES[r])
                continue
            rr = sw.periodo(ref, ini, fim).reindex(d.index)["ret"]
            m = sw.medidas(d["ret"], rr, d["cdi"])
            vered.setdefault(r, {})[nome_p] = m
            p(sw.linha(NOMES[r], m))
    p("")
    p("VEREDITO (registrado: acima da referência no treino E no teste, e Sharpe maior que o dela no teste;")
    p("          evidência forte só com t > %.2f no teste, por serem 6 hipóteses mensais)" % T_FORTE)
    for r in REGRAS:
        tr, te = vered.get(r, {}).get("TREINO"), vered.get(r, {}).get("TESTE")
        rte = vered.get("referencia", {}).get("TESTE")
        if not (tr and te and rte):
            p("  %-24s dados insuficientes" % NOMES[r])
            continue
        passa = tr["acima_ref_aa"] > 0 and te["acima_ref_aa"] > 0 and te["sharpe"] > rte["sharpe"]
        forte = passa and te["t_vs_ref"] > T_FORTE
        txt = ("APROVADA com evidência forte" if forte else "APROVADA, evidência fraca") if passa else "REPROVADA"
        p("  %-24s %s (treino %+.1f p.p., teste %+.1f p.p. a.a. vs referência, t=%+.1f; Sharpe teste %.2f vs %.2f)"
          % (NOMES[r], txt, tr["acima_ref_aa"], te["acima_ref_aa"], te["t_vs_ref"], te["sharpe"], rte["sharpe"]))
    p("")
    p("Limitações: ações que existem hoje (viés de sobrevivência); empresas com ON e PN usam o preço de uma")
    p("classe para o valor de mercado. Aprovada aqui ainda precisa do teste para frente.")
    p("Não é recomendação de investimento.")
    texto = "\n".join(saida)
    print(texto)
    if not (a.demo or a.demo_padrao):
        with open("resultado_fatores.txt", "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
        tab = pd.DataFrame({NOMES[r]: res[r]["ret"] for r in res if not res[r].empty})
        tab["CDI"] = ref["cdi"]
        tab.to_csv("retornos_mensais_fatores.csv", sep=";", decimal=",")
        notas.to_csv("fundamentos_mensais.csv", sep=";", decimal=",", index=False)
    return res, notas


if __name__ == "__main__":
    main()
