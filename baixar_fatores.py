#!/usr/bin/env python3
"""Baixa os dados da pesquisa de fatores (HIPOTESES_FATORES.md). Só biblioteca padrão.

  - Balanços da CVM (dados abertos): ITR (trimestral) e DFP (anual), 2010 até hoje,
    só das empresas de trader/universe.txt (DRE, balanço passivo, composição do capital e
    a data de entrega de cada documento).
  - Ligação código de negociação -> CNPJ (formulário FCA da CVM).
  - Preços diários do Yahoo (fechamento, fechamento ajustado e desdobramentos), 2010 até hoje.
  - CDI diário do Banco Central.

Tudo vai para a pasta dados_fatores. Leva de 5 a 20 minutos, conforme a internet
(os arquivos da CVM são grandes; depois de lidos, são apagados e só fica o que interessa).

  python baixar_fatores.py
"""
import csv
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "dados_fatores")
CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/%s/DADOS/%s_cia_aberta_%d.zip"
YAHOO = ("https://query1.finance.yahoo.com/v8/finance/chart/%s.SA?interval=1d&period1=1262304000"
         "&period2=%d&events=div%%7Csplit")
BCB = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
       "&dataInicial=%s&dataFinal=%s")
UA = {"User-Agent": "Mozilla/5.0 (compatible; day-trade-b3/1.0; estudo)"}
PARTES = ("DRE_con", "DRE_ind", "BPP_con", "BPP_ind", "composicao_capital")


def baixar(url, destino=None, tentativas=4):
    """Baixa a URL. Com destino, grava em disco e devolve o caminho; sem, devolve os bytes."""
    for i in range(tentativas):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                if destino is None:
                    return r.read()
                with open(destino + ".parcial", "wb") as fh:
                    while True:
                        bloco = r.read(1 << 20)
                        if not bloco:
                            break
                        fh.write(bloco)
            os.replace(destino + ".parcial", destino)
            return destino
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1))
        except Exception:  # noqa: BLE001  (rede instável: tenta de novo)
            time.sleep(3 * (i + 1))
    return None


def lista_acoes():
    with open(os.path.join(AQUI, "trader", "universe.txt"), encoding="utf-8") as fh:
        return [ln.split("|")[0].strip().upper() for ln in fh if ln.strip() and not ln.startswith("#")]


def linhas_csv(zf, membro):
    with zf.open(membro) as bruto:
        texto = io.TextIOWrapper(bruto, encoding="latin-1", newline="")
        yield from csv.reader(texto, delimiter=";")


def col(cab, *nomes):
    baixo = [c.strip().lower() for c in cab]
    for n in nomes:
        if n.lower() in baixo:
            return baixo.index(n.lower())
    for n in nomes:
        for i, c in enumerate(baixo):
            if n.lower() in c:
                return i
    return None


# ------------------------------------------------------------------ 1. código -> CNPJ
def mapear_tickers(acoes, ano_atual, cache):
    mapa, raiz = {}, {}
    for ano in range(ano_atual, 2016, -1):  # do mais novo para o mais velho: vale o mais recente
        zpath = os.path.join(cache, "fca_%d.zip" % ano)
        if not (os.path.exists(zpath) or baixar(CVM % ("FCA", "fca", ano), zpath)):
            continue
        try:
            with zipfile.ZipFile(zpath) as zf:
                for m in zf.namelist():
                    if "valor_mobiliario" not in m.lower():
                        continue
                    it = linhas_csv(zf, m)
                    cab = next(it)
                    ic, it_cod = col(cab, "CNPJ_Companhia", "cnpj"), col(cab, "Codigo_Negociacao", "negociacao")
                    if ic is None or it_cod is None:
                        print("  aviso: colunas inesperadas em %s: %s" % (m, cab))
                        continue
                    for r in it:
                        if len(r) <= max(ic, it_cod):
                            continue
                        cod = r[it_cod].strip().upper()
                        if cod and cod not in mapa:
                            mapa[cod] = r[ic].strip()
                        if len(cod) >= 4 and cod[:4] not in raiz:
                            raiz[cod[:4]] = r[ic].strip()
        except zipfile.BadZipFile:
            print("  aviso: arquivo FCA %d corrompido" % ano)
        os.remove(zpath)
    saida, faltam = {}, []
    for a in acoes:
        if a in mapa:
            saida[a] = (mapa[a], "codigo")
        elif a[:4] in raiz:
            saida[a] = (raiz[a[:4]], "raiz do codigo")
        else:
            faltam.append(a)
    with open(os.path.join(PASTA, "mapa_tickers.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["ticker", "cnpj", "como"])
        for a, (c, como) in sorted(saida.items()):
            w.writerow([a, c, como])
    return saida, faltam


# ------------------------------------------------------------------ 2. balanços
def extrair_balancos(cnpjs, ano_atual, cache, desde=2010):
    destino = os.path.join(PASTA, "cvm")
    os.makedirs(destino, exist_ok=True)
    resumo = []
    for tipo in ("DFP", "ITR"):
        for ano in range(desde, ano_atual + 1):
            saida_ok = os.path.join(destino, "%s_%d.ok" % (tipo, ano))
            if os.path.exists(saida_ok) and ano < ano_atual:
                print("  %s %d: já baixado" % (tipo, ano))
                continue
            print("  %s %d: baixando..." % (tipo, ano), end="", flush=True)
            zpath = os.path.join(cache, "%s_%d.zip" % (tipo.lower(), ano))
            if not baixar(CVM % (tipo, tipo.lower(), ano), zpath):
                print(" não existe ou falhou")
                continue
            n_linhas = 0
            try:
                with zipfile.ZipFile(zpath) as zf:
                    for m in zf.namelist():
                        base = os.path.basename(m)
                        if base.lower() == ("%s_cia_aberta_%d.csv" % (tipo.lower(), ano)):
                            parte = "indice"
                        else:
                            parte = next((p for p in PARTES if p.lower() in base.lower()), None)
                        if not parte:
                            continue
                        it = linhas_csv(zf, m)
                        cab = next(it)
                        ic = col(cab, "CNPJ_CIA", "cnpj")
                        if ic is None:
                            print("\n  aviso: sem coluna de CNPJ em %s" % base)
                            continue
                        with gzip.open(os.path.join(destino, "%s_%s_%d.csv.gz" % (tipo, parte, ano)), "wt",
                                       encoding="utf-8", newline="") as gz:
                            w = csv.writer(gz, delimiter=";")
                            w.writerow(cab)
                            for r in it:
                                if len(r) > ic and r[ic].strip() in cnpjs:
                                    w.writerow(r)
                                    n_linhas += 1
            except zipfile.BadZipFile:
                print(" arquivo corrompido; rode de novo depois")
                os.remove(zpath)
                continue
            os.remove(zpath)
            open(saida_ok, "w").close()
            print(" ok (%d linhas das nossas empresas)" % n_linhas)
            resumo.append((tipo, ano, n_linhas))
    return resumo


# ------------------------------------------------------------------ 3. preços e CDI
def baixar_precos(acoes):
    destino = os.path.join(PASTA, "precos")
    os.makedirs(destino, exist_ok=True)
    agora = int(time.time())
    ok, falhas = 0, []
    for i, a in enumerate(acoes, 1):
        bruto = baixar(YAHOO % (a, agora))
        try:
            res = json.loads(bruto.decode("utf-8"))["chart"]["result"][0] if bruto else None
        except (ValueError, KeyError, TypeError, IndexError):
            res = None
        if not res or not res.get("timestamp"):
            falhas.append(a)
            continue
        with gzip.open(os.path.join(destino, a + ".json.gz"), "wt", encoding="utf-8") as fh:
            json.dump(res, fh)
        ok += 1
        if i % 10 == 0:
            print("  preços: %d de %d" % (i, len(acoes)), flush=True)
        time.sleep(0.3)
    return ok, falhas


def baixar_cdi():
    linhas = []
    ini = dt.date(2010, 1, 1)
    hoje = dt.date.today()
    while ini <= hoje:
        fim = min(dt.date(ini.year + 4, 12, 31), hoje)  # o BC limita a 10 anos por consulta
        bruto = baixar(BCB % (ini.strftime("%d/%m/%Y"), fim.strftime("%d/%m/%Y")))
        if bruto:
            for x in json.loads(bruto.decode("utf-8")):
                linhas.append((dt.datetime.strptime(x["data"], "%d/%m/%Y").date().isoformat(), x["valor"]))
        ini = fim + dt.timedelta(days=1)
    with open(os.path.join(PASTA, "cdi.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["data", "cdi_pct_ao_dia"])
        w.writerows(sorted(set(linhas)))
    return len(linhas)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=2010, help="primeiro ano de balanços (padrão 2010)")
    a = ap.parse_args(argv)
    os.makedirs(PASTA, exist_ok=True)
    cache = os.path.join(PASTA, "_baixando")
    os.makedirs(cache, exist_ok=True)
    acoes = lista_acoes()
    ano_atual = dt.date.today().year
    print("1/4 Ligando códigos das ações aos CNPJs (formulário FCA da CVM)...", flush=True)
    mapa, faltam = mapear_tickers(acoes, ano_atual, cache)
    print("  %d de %d ações ligadas a um CNPJ.%s" % (len(mapa), len(acoes),
                                                    (" Sem CNPJ: " + ", ".join(faltam)) if faltam else ""))
    if not mapa:
        sys.exit("Não consegui ler o FCA da CVM. Confira a internet e rode de novo.")
    cnpjs = {c for c, _ in mapa.values()}
    print("\n2/4 Balanços da CVM (DFP anual e ITR trimestral, 2010 até hoje)...", flush=True)
    resumo = extrair_balancos(cnpjs, ano_atual, cache, a.desde)
    print("\n3/4 Preços diários (Yahoo)...", flush=True)
    ok, falhas = baixar_precos(acoes)
    print("  %d de %d ações com preço.%s" % (ok, len(acoes), (" Sem preço: " + ", ".join(falhas)) if falhas else ""))
    print("\n4/4 CDI (Banco Central)...", flush=True)
    n_cdi = baixar_cdi()
    print("  %d dias de CDI." % n_cdi)
    with open(os.path.join(PASTA, "LEIA.txt"), "w", encoding="utf-8") as fh:
        fh.write("Baixado em %s\nAções com CNPJ: %d\nAções com preço: %d\nDias de CDI: %d\n"
                 % (dt.datetime.now().strftime("%d/%m/%Y %H:%M"), len(mapa), ok, n_cdi))
        for tipo, ano, n in resumo:
            fh.write("%s %d: %d linhas\n" % (tipo, ano, n))
    try:
        os.rmdir(cache)
    except OSError:
        pass
    print("\nPronto. Tudo em dados_fatores. Avise o Claude para rodar a pesquisa.")


if __name__ == "__main__":
    main()
