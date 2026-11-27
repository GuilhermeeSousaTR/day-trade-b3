#!/usr/bin/env python3
"""Pesquisa de day trade: testa H1, H2 e H3, registradas em HIPOTESES_DAYTRADE.md
ANTES de ver os dados. Só biblioteca padrão. Só lê dados; não envia ordens.

  py -3.14 mt5_ponte.py historico          (antes: anos de barras de 5 min do MetaTrader)
  python pesquisa_daytrade.py              (usa dados_mt5_longo)
  python pesquisa_daytrade.py --demo       (dados falsos SEM padrão: as três devem ser reprovadas)
  python pesquisa_daytrade.py --demo-padrao  (dados falsos COM reversão de gap: H1 deve passar)

Saídas: resultado_daytrade.txt e operacoes_daytrade.csv (abre no Excel/Power BI).
"""
import argparse
import collections
import csv
import datetime as dt
import glob
import gzip
import json
import os
import random
import statistics
import sys

CUSTO = 0.001            # 0,10% ida e volta
CUSTOS_INFO = (0.0005, 0.002)
N_HIP = 3
NIVEL = 1 - 0.05 / N_HIP  # 98,3% (Bonferroni)
MIN_OPS_TESTE = 300
M5 = dt.timedelta(minutes=5)
NOMES = {"H1": "H1 Reversão do gap", "H2": "H2 Momento do dia", "H3": "H3 Reversão entre ações"}


# ------------------------------------------------------------------ dados
def _barras_csv(caminho):
    with gzip.open(caminho, "rt", encoding="utf-8") as fh:
        leitor = csv.reader(fh)
        next(leitor, None)  # cabeçalho: ts_utc, open, high, low, close, volume
        for r in leitor:
            yield (int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]))


def _barras_json(caminho):
    r = json.load(open(caminho, encoding="utf-8"))["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    for i, t in enumerate(r["timestamp"]):
        v = (q["open"][i], q["high"][i], q["low"][i], q["close"][i])
        if None not in v:
            yield (int(t),) + tuple(float(x) for x in v)


def ler_acao(f):
    """{dia: {hora_inicio_barra: (o, h, l, c)}} de uma ação, no horário de Brasília (UTC-3)."""
    nome = os.path.basename(f)
    leitor = _barras_csv if nome.endswith(".csv.gz") else _barras_json
    dias = collections.defaultdict(dict)
    for ts, o, h, l, c in leitor(f):
        t = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=ts - 3 * 3600)
        if dt.time(10, 0) <= t.time() <= dt.time(18, 0):
            dias[t.date()][t.time()] = (o, h, l, c)
    return dict(dias)


class Pasta:
    """Lê uma ação por vez (5 anos de 80 ações não cabem folgados na memória de uma vez)."""
    def __init__(self, pasta):
        self.arquivos = sorted(glob.glob(os.path.join(pasta, "*.csv.gz"))) or sorted(
            f for f in glob.glob(os.path.join(pasta, "*.json")) if not os.path.basename(f).startswith("varredura"))

    def __len__(self):
        return len(self.arquivos)

    def items(self):
        for f in self.arquivos:
            dias = ler_acao(f)
            if dias:
                yield os.path.basename(f).split(".")[0], dias


def carregar_pasta(pasta):
    """{acao: {dia: {hora_inicio_barra: (o, h, l, c)}}} no horário de Brasília (UTC-3)."""
    dados = {}
    arquivos = sorted(glob.glob(os.path.join(pasta, "*.csv.gz"))) or sorted(
        f for f in glob.glob(os.path.join(pasta, "*.json")) if not os.path.basename(f).startswith("varredura"))
    for f in arquivos:
        nome = os.path.basename(f)
        sym = nome.split(".")[0]
        leitor = _barras_csv if nome.endswith(".csv.gz") else _barras_json
        dias = collections.defaultdict(dict)
        for ts, o, h, l, c in leitor(f):
            t = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=ts - 3 * 3600)
            if dt.time(10, 0) <= t.time() <= dt.time(18, 0):
                dias[t.date()][t.time()] = (o, h, l, c)
        if dias:
            dados[sym] = dict(dias)
    return dados


def fim_por_dia(dados):
    """Fim do pregão contínuo de cada dia, descoberto pelos dados: a última barra que a maioria
    das ações tem (é a do leilão de fechamento) começa 5 min antes do fim."""
    cont = collections.defaultdict(collections.Counter)
    n = collections.Counter()
    for _, dias in dados.items():
        for d, barras in dias.items():
            n[d] += 1
            for t in barras:
                cont[d][t] += 1
    fim = {}
    for d, c in cont.items():
        if n[d] < 3:
            continue
        ok = [t for t, k in c.items() if k >= 0.6 * n[d] and t >= dt.time(14, 0)]
        if ok:
            ult = dt.datetime.combine(d, max(ok)) + M5
            fim[d] = ult.time()
    return fim


def _t(d, hora, minutos=0):
    return (dt.datetime.combine(d, hora) + dt.timedelta(minutes=minutos)).time()


# ------------------------------------------------------------------ hipóteses
def _simular_saida(barras, d, desde, ate, direcao, entrada, stop, alvo):
    """Percorre as barras com início em (desde, ate]; stop tem prioridade (conservador)."""
    t = _t(d, desde, 5)
    ultimo = entrada
    while t <= ate:
        b = barras.get(t)
        if b:
            o, h, l, c = b
            if direcao > 0:
                if l <= stop:
                    return min(o, stop), "stop"
                if h >= alvo:
                    return alvo, "alvo"
            else:
                if h >= stop:
                    return max(o, stop), "stop"
                if l <= alvo:
                    return alvo, "alvo"
            ultimo = c
        t = _t(d, t, 5)
    return ultimo, "fechamento"


def gerar_operacoes(dados, fim):
    ops = []
    dias_ord = sorted(fim)
    anterior = {d: dias_ord[i - 1] for i, d in enumerate(dias_ord) if i > 0}
    h3_dia = collections.defaultdict(list)
    for sym, dias in dados.items():
        for d, barras in dias.items():
            if d not in fim or d not in anterior:
                continue
            C = fim[d]
            ult_barra = _t(d, C, -10)       # barra que termina 5 min antes do fim
            sai = barras.get(ult_barra)
            b10 = barras.get(dt.time(10, 0))
            if not sai or not b10:
                continue
            dp = anterior[d]
            if (d - dp).days > 7 or dp not in dias:
                continue
            fech_ant = dias[dp].get(_t(dp, fim[dp], -5)) or dias[dp].get(_t(dp, fim[dp], -10))
            if not fech_ant:
                continue
            pc = fech_ant[3]
            # H1: reversão do gap
            gap = b10[0] / pc - 1
            if 0.01 <= abs(gap) <= 0.05:
                e = b10[3]
                direcao = -1 if gap > 0 else 1
                dist = (pc - e) * direcao
                if dist > 0:
                    stop = e - direcao * dist
                    s, como = _simular_saida(barras, d, dt.time(10, 0), ult_barra, direcao, e, stop, pc)
                    ops.append({"hip": "H1", "dia": d, "acao": sym, "lado": direcao, "entrada": e,
                                "saida": s, "como": como, "bruto": direcao * (s / e - 1)})
            # H2: momento do dia
            b1025 = barras.get(dt.time(10, 25))
            ent = barras.get(_t(d, C, -35))
            if b1025 and ent:
                r1 = b1025[3] / pc - 1
                if abs(r1) >= 0.005:
                    direcao = 1 if r1 > 0 else -1
                    e, s = ent[3], sai[3]
                    ops.append({"hip": "H2", "dia": d, "acao": sym, "lado": direcao, "entrada": e,
                                "saida": s, "como": "fechamento", "bruto": direcao * (s / e - 1)})
            # H3: guarda o retorno da 1ª hora para ranquear depois
            b1055 = barras.get(dt.time(10, 55))
            if b1055:
                h3_dia[d].append((b1055[3] / b10[0] - 1, sym, b1055[3], sai[3]))
    for d, lst in h3_dia.items():
        if len(lst) < 20:
            continue
        lst.sort()
        k = max(2, len(lst) // 10)
        for direcao, grupo in ((1, lst[:k]), (-1, lst[-k:])):
            for _, sym, e, s in grupo:
                ops.append({"hip": "H3", "dia": d, "acao": sym, "lado": direcao, "entrada": e,
                            "saida": s, "como": "fechamento", "bruto": direcao * (s / e - 1)})
    return ops


# ------------------------------------------------------------------ estatística
def resumo(ops, custo=CUSTO, sorteios=2000, semente=7):
    if not ops:
        return None
    por = collections.defaultdict(lambda: [0.0, 0])
    for o in ops:
        x = por[o["dia"]]
        x[0] += o["bruto"] - custo
        x[1] += 1
    dias = list(por.values())
    rng = random.Random(semente)
    medias = []
    for _ in range(sorteios):
        s = n = 0
        for _ in dias:
            a, b = dias[rng.randrange(len(dias))]
            s += a
            n += b
        medias.append(s / n)
    medias.sort()
    q = lambda p: 100 * medias[min(len(medias) - 1, max(0, int(p * len(medias))))]
    rs = [o["bruto"] - custo for o in ops]
    return {"n": len(rs), "dias": len(dias), "media": 100 * statistics.fmean(rs),
            "acerto": 100 * sum(r > 0 for r in rs) / len(rs),
            "ic95": (q(0.025), q(0.975)), "icb": (q((1 - NIVEL) / 2), q(1 - (1 - NIVEL) / 2))}


def fmt(s):
    if not s:
        return "sem operações"
    return ("%6d ops em %4d dias | acerto %5.1f%% | média %+.3f%% | IC95 %+.3f a %+.3f | IC98,3 %+.3f a %+.3f"
            % (s["n"], s["dias"], s["acerto"], s["media"], s["ic95"][0], s["ic95"][1], s["icb"][0], s["icb"][1]))


def avaliar(ops, corte, out):
    tabela = []
    for h in ("H1", "H2", "H3"):
        oh = [o for o in ops if o["hip"] == h]
        tr = resumo([o for o in oh if o["dia"] < corte])
        te = resumo([o for o in oh if o["dia"] >= corte])
        out("\n" + "-" * 100)
        out(NOMES[h])
        out("  Treino: " + fmt(tr))
        out("  Teste:  " + fmt(te))
        if te:
            for c in CUSTOS_INFO:
                x = resumo([o for o in oh if o["dia"] >= corte], custo=c, sorteios=300)
                out("    (informativo) teste com custo %.2f%%: média %+.3f%%" % (100 * c, x["media"]))
            for lado, nome in ((1, "compras"), (-1, "vendas")):
                x = resumo([o for o in oh if o["dia"] >= corte and o["lado"] == lado], sorteios=300)
                if x:
                    out("    (informativo) teste só %s: %d ops, média %+.3f%%" % (nome, x["n"], x["media"]))
            anos = collections.defaultdict(list)
            for o in oh:
                anos[o["dia"].year].append(100 * (o["bruto"] - CUSTO))
            out("    Por ano: " + " | ".join("%d %+.3f%% (%d)" % (a, statistics.fmean(v), len(v))
                                             for a, v in sorted(anos.items())))
        motivos = []
        if not tr or tr["media"] <= 0:
            motivos.append("média do treino não é positiva")
        if not te or te["media"] <= 0:
            motivos.append("média do teste não é positiva")
        if te and te["icb"][0] <= 0:
            motivos.append("no teste, o IC 98,3% inclui zero ou negativo (pode ser sorte)")
        if not te or te["n"] < MIN_OPS_TESTE:
            motivos.append("menos de %d operações no teste" % MIN_OPS_TESTE)
        veredito = "APROVADA para o teste na conta demo" if not motivos else "REPROVADA"
        out("  VEREDITO: " + veredito + ("" if not motivos else " (" + "; ".join(motivos) + ")"))
        tabela.append((h, tr, te, veredito))
    return tabela


# ------------------------------------------------------------------ dados falsos para validar
def dados_falsos(padrao, n_acoes=40, n_dias=600, semente=11):
    rng = random.Random(semente)
    dados = {}
    d0 = dt.date(2023, 1, 2)
    dias = []
    d = d0
    while len(dias) < n_dias:
        if d.weekday() < 5:
            dias.append(d)
        d += dt.timedelta(days=1)
    mercado = {d: [rng.gauss(0, 0.0012) for _ in range(96)] for d in dias}
    for k in range(n_acoes):
        sym = "FAKE%02d" % k
        p = 20.0
        out = {}
        for d in dias:
            gap = rng.gauss(0, 0.015)
            p *= 1 + gap
            barras = {}
            t = dt.datetime.combine(d, dt.time(10, 0))
            fim = dt.datetime.combine(d, dt.time(17, 55))
            i = 0
            while t < fim:
                r = rng.gauss(0, 0.002) + mercado[d][i]
                if padrao and i < 40 and abs(gap) >= 0.01:
                    r -= gap * 0.02  # devolve parte do gap ao longo do dia
                o = p
                c = p * (1 + r)
                h = max(o, c) * (1 + abs(rng.gauss(0, 0.0008)))
                l = min(o, c) * (1 - abs(rng.gauss(0, 0.0008)))
                barras[t.time()] = (o, h, l, c)
                p = c
                t += M5
                i += 1
            out[d] = barras
        dados[sym] = out
    return dados


# ------------------------------------------------------------------ principal
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pasta", default="dados_mt5_longo")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--demo-padrao", action="store_true")
    a = ap.parse_args(argv)
    linhas = []

    def out(s=""):
        print(s)
        linhas.append(s)

    if a.demo or a.demo_padrao:
        dados = dados_falsos(a.demo_padrao)
        fonte = "DADOS FALSOS (%s)" % ("com reversão de gap plantada" if a.demo_padrao else "sem nenhum padrão")
    else:
        if not os.path.isdir(a.pasta):
            sys.exit("Não achei a pasta %s. Rode antes: py -3.14 mt5_ponte.py historico" % a.pasta)
        dados = Pasta(a.pasta)
        print("Lendo %d ações (1ª passada: calendário)..." % len(dados), flush=True)
        fonte = "MetaTrader (%s)" % a.pasta
    if not dados:
        sys.exit("Nenhum dado encontrado.")
    fim = fim_por_dia(dados)
    if not fim:
        sys.exit("Os dados não têm pregões suficientes.")
    if not (a.demo or a.demo_padrao):
        print("2ª passada: operações de cada ação...", flush=True)
    dias = sorted(fim)
    corte = dias[2 * len(dias) // 3]
    ops = gerar_operacoes(dados, fim)

    out("PESQUISA DE DAY TRADE (hipóteses registradas em 24/11/2026, HIPOTESES_DAYTRADE.md)")
    out("Fonte: %s | %d ações | %d pregões de %s a %s" % (fonte, len(dados), len(dias),
                                                           dias[0].strftime("%d/%m/%Y"), dias[-1].strftime("%d/%m/%Y")))
    out("Treino: até %s | Teste: de %s em diante | custo %.2f%% por operação"
        % ((corte - dt.timedelta(days=1)).strftime("%d/%m/%Y"), corte.strftime("%d/%m/%Y"), 100 * CUSTO))
    fins = collections.Counter((d.year, fim[d].strftime("%H:%M")) for d in dias)
    out("Fim do pregão descoberto nos dados (ano: horário x dias): " + "; ".join(
        "%d: %s" % (ano, ", ".join("%s x%d" % (h, k) for (y, h), k in sorted(fins.items()) if y == ano))
        for ano in sorted({y for y, _ in fins})))
    tabela = avaliar(ops, corte, out)
    out("\n" + "=" * 100)
    aprov = [NOMES[h] for h, _, _, v in tabela if v.startswith("APROVADA")]
    if aprov:
        out("Aprovadas: " + ", ".join(aprov) + ". Próximo passo: teste para frente na conta DEMO (robo_demo.py).")
    else:
        out("Nenhuma hipótese aprovada. Isso também é resultado: evita perder dinheiro com regra que não funciona.")
    out("Viés de sobrevivência: as ações são as líquidas de hoje, o que favorece os resultados.")
    out("Não é recomendação de investimento.")
    if not (a.demo or a.demo_padrao):
        with open("resultado_daytrade.txt", "w", encoding="utf-8") as fh:
            fh.write("\n".join(linhas) + "\n")
        with open("operacoes_daytrade.csv", "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["hipotese", "data", "acao", "lado", "entrada", "saida", "como_terminou",
                        "resultado_pct_com_custo", "periodo"])
            for o in sorted(ops, key=lambda o: (o["hip"], o["dia"], o["acao"])):
                w.writerow([o["hip"], o["dia"].isoformat(), o["acao"], "compra" if o["lado"] > 0 else "venda",
                            ("%.2f" % o["entrada"]).replace(".", ","), ("%.2f" % o["saida"]).replace(".", ","),
                            o["como"], ("%.3f" % (100 * (o["bruto"] - CUSTO))).replace(".", ","),
                            "treino" if o["dia"] < corte else "teste"])
        out("\nGravados: resultado_daytrade.txt e operacoes_daytrade.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
