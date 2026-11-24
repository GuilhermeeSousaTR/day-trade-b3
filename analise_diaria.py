#!/usr/bin/env python3
"""Análise diária do diário de sinais (teste PARA FRENTE do rompimento da abertura).

Lê diario_sinais.csv (gravado pelo diario.py) e responde, em português simples:
  1. Como foi o último pregão?
  2. Qual a tendência, pregão a pregão?
  3. O resultado para frente confirma ou contradiz o backtest?
  4. Algum filtro está se destacando (só acompanhamento: nenhum foi aprovado)?
  5. Quais ações mais ajudaram e atrapalharam?
  6. Check-up: faltou algum pregão no diário?

Também grava analise/por_dia.csv (abre no Excel ou no Power BI).
Só lê dados; não envia ordens. Não é recomendação de investimento.

  python analise_diaria.py
  python analise_diaria.py --hoje 2026-11-24     (para testar como se fosse outro dia)
"""
import csv
import datetime as dt
import importlib.util
import os
import random
import statistics

AQUI = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(AQUI, "diario_sinais.csv")
SAIDA = os.path.join(AQUI, "analise", "por_dia.csv")
INICIO = dt.date(2026, 11, 23)
META_PREGOES = 40
FILTROS = ["mercado_em_alta", "volume_alto", "sem_gap", "faixa_estreita"]
# Backtest com dados reais do MetaTrader (82 ações, 30/07 a 19/11/2026, 2.624 operações, custo 0,10%)
BACKTEST_MEDIA = -0.082  # % por operação
BACKTEST_IC = (-0.166, -0.000)


def _sessao():
    spec = importlib.util.spec_from_file_location("b3exit", os.path.join(AQUI, "trader-exit", "exit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.session


def hoje_brasilia():
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()


def num(s):
    return float(s.replace(",", "."))


def br(x, casas=2):
    return ("%+.*f" % (casas, x)).replace(".", ",")


def carregar():
    ops = []
    if not os.path.exists(ARQ):
        return ops
    with open(ARQ, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter=";"):
            try:
                o = {"dia": dt.date.fromisoformat(r["data"]), "acao": r["acao"], "hora": r["hora_entrada"],
                     "como": r["como_terminou"], "ret": num(r["resultado_pct"])}
            except (KeyError, ValueError):
                continue
            for f in FILTROS:
                o[f] = r.get(f) == "sim"
            ops.append(o)
    return ops


def stats(ops):
    if not ops:
        return None
    rs = [o["ret"] for o in ops]
    ganhos = [r for r in rs if r > 0]
    return {"n": len(rs), "acerto": 100.0 * len(ganhos) / len(rs), "media": statistics.fmean(rs), "soma": sum(rs)}


def ic_por_dias(ops, reps=2000, semente=42):
    """IC 95% da média por operação, sorteando pregões inteiros (dias são correlacionados)."""
    por = {}
    for o in ops:
        por.setdefault(o["dia"], []).append(o["ret"])
    dias = list(por.values())
    if len(dias) < 5:
        return None
    rnd = random.Random(semente)
    medias = []
    for _ in range(reps):
        amostra = [rnd.choice(dias) for _ in dias]
        tot = sum(sum(d) for d in amostra)
        n = sum(len(d) for d in amostra)
        medias.append(tot / n)
    medias.sort()
    return medias[int(0.025 * reps)], medias[int(0.975 * reps) - 1]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--hoje", help="AAAA-MM-DD (só para teste)")
    a = ap.parse_args(argv)
    hoje = dt.date.fromisoformat(a.hoje) if a.hoje else hoje_brasilia()

    ops = [o for o in carregar() if o["dia"] <= hoje]
    print("=" * 72)
    print("ANÁLISE DIÁRIA (%s). Teste para frente do rompimento da abertura." % hoje.strftime("%d/%m/%Y"))
    print("=" * 72)
    if not ops:
        print("Diário ainda vazio. O primeiro pregão entra depois do fechamento.")
        return 0

    dias = sorted({o["dia"] for o in ops})
    print("Pregões no diário: %d de %d necessários para a 1ª conclusão firme." % (len(dias), META_PREGOES))

    # 1. último pregão
    ult = dias[-1]
    oh = [o for o in ops if o["dia"] == ult]
    s = stats(oh)
    print("\n1) ÚLTIMO PREGÃO (%s)" % ult.strftime("%d/%m"))
    print("   %d sinais | acerto %.0f%% | média %s%% por operação | soma %s%%"
          % (s["n"], s["acerto"], br(s["media"], 3), br(s["soma"])))
    print("   Em dinheiro de mentira: R$ 1.000 em cada sinal daria %s no dia."
          % br(10 * s["soma"]).replace("+", "+R$ ").replace("-", "-R$ "))
    como = {}
    for o in oh:
        como[o["como"]] = como.get(o["como"], 0) + 1
    print("   Como terminaram: " + ", ".join("%s %d" % (k, v) for k, v in sorted(como.items())))
    melhor = max(oh, key=lambda o: o["ret"])
    pior = min(oh, key=lambda o: o["ret"])
    print("   Melhor: %s %s%% (%s) | Pior: %s %s%% (%s)"
          % (melhor["acao"], br(melhor["ret"]), melhor["como"], pior["acao"], br(pior["ret"]), pior["como"]))

    # 2. tendência
    print("\n2) PREGÃO A PREGÃO (cada linha é um dia)")
    print("   %-6s %5s %8s %10s %12s" % ("dia", "ops", "acerto", "média", "acumulado"))
    linhas, acum, pico, queda = [], 0.0, 0.0, 0.0
    for d in dias:
        sd = stats([o for o in ops if o["dia"] == d])
        acum += sd["media"]  # carteira que divide o dinheiro igualmente entre os sinais do dia
        pico = max(pico, acum)
        queda = min(queda, acum - pico)
        linhas.append((d, sd, acum))
    for d, sd, ac in linhas[-10:]:
        print("   %-6s %5d %7.0f%% %9s%% %11s%%" % (d.strftime("%d/%m"), sd["n"], sd["acerto"],
                                                 br(sd["media"], 3), br(ac)))
    if len(linhas) > 10:
        print("   (mostrando os 10 últimos de %d; todos estão em analise/por_dia.csv)" % len(linhas))
    positivos = sum(1 for _, sd, _ in linhas if sd["media"] > 0)
    print("   Dias positivos: %d de %d | maior queda da curva: %s%%" % (positivos, len(linhas), br(queda)))
    if len(linhas) >= 6:
        ult5 = statistics.fmean(sd["media"] for _, sd, _ in linhas[-5:])
        antes = statistics.fmean(sd["media"] for _, sd, _ in linhas[:-5])
        print("   Média dos últimos 5 pregões: %s%% (antes deles: %s%%)" % (br(ult5, 3), br(antes, 3)))

    # 3. comparação com o backtest
    st = stats(ops)
    ic = ic_por_dias(ops)
    print("\n3) PARA FRENTE x BACKTEST")
    print("   Backtest (30/07 a 19/11, 2.624 ops): média %s%% por operação (IC95 %s a %s)"
          % (br(BACKTEST_MEDIA, 3), br(BACKTEST_IC[0], 3), br(BACKTEST_IC[1], 3)))
    print("   Para frente (%d ops): média %s%% | acerto %s%%" % (st["n"], br(st["media"], 3), ("%.1f" % st["acerto"]).replace(".", ",")))
    if ic is None:
        leitura = "ainda não dá para medir a incerteza (precisa de pelo menos 5 pregões)."
    else:
        print("   IC95 para frente (sorteando dias inteiros): %s a %s%%" % (br(ic[0], 3), br(ic[1], 3)))
        if ic[0] > 0:
            leitura = "LUCRO ACIMA DO ACASO para frente. Raro e importante: confirme com mais pregões antes de qualquer conclusão."
        elif ic[0] > BACKTEST_MEDIA:
            leitura = "melhor que o backtest previa, mas ainda sem provar lucro (o intervalo inclui zero)."
        elif ic[1] < BACKTEST_MEDIA:
            leitura = "PIOR que o backtest previa. A regra está perdendo mais do que o esperado."
        else:
            leitura = "dentro do que o backtest previa: perda pequena e constante, compatível com custo comendo o ganho."
    print("   Leitura: " + leitura)

    # 4. filtros
    print("\n4) FILTROS (só acompanhamento: nenhum passou no teste histórico)")
    for f in FILTROS:
        com = stats([o for o in ops if o[f]])
        sem = stats([o for o in ops if not o[f]])
        if not com or not sem:
            continue
        print("   %-16s com: %4d ops %s%% | sem: %4d ops %s%% | diferença %s p.p."
              % (f, com["n"], br(com["media"], 3), sem["n"], br(sem["media"], 3), br(com["media"] - sem["media"], 3)))
    if len(dias) < META_PREGOES:
        print("   Com menos de %d pregões, diferenças entre filtros são quase só sorte." % META_PREGOES)

    # 5. ações
    por = {}
    for o in ops:
        por.setdefault(o["acao"], []).append(o["ret"])
    elegiveis = [(k, sum(v), len(v)) for k, v in por.items() if len(v) >= 3]
    print("\n5) AÇÕES (soma dos resultados, só as com 3+ operações)")
    if len(elegiveis) >= 6:
        elegiveis.sort(key=lambda t: t[1])
        print("   Mais ajudaram: " + ", ".join("%s %s%% (%d)" % (k, br(sm), n) for k, sm, n in elegiveis[::-1][:3]))
        print("   Mais atrapalharam: " + ", ".join("%s %s%% (%d)" % (k, br(sm), n) for k, sm, n in elegiveis[:3]))
        print("   Aviso: com poucas operações por ação, isso é ruído. Não serve para escolher ações.")
    else:
        print("   Ainda poucas ações com 3+ operações.")

    # 6. check-up
    print("\n6) CHECK-UP")
    try:
        sessao = _sessao()
        esperados, d = [], INICIO
        while d < hoje:  # o pregão de hoje só entra depois do fechamento
            if sessao(d):
                esperados.append(d)
            d += dt.timedelta(days=1)
        faltando = [x for x in esperados if x not in set(dias)]
        if faltando:
            print("   ATENÇÃO: pregões sem registro no diário: " + ", ".join(x.strftime("%d/%m") for x in faltando))
            print("   (o agente da noite pode ter falhado nesses dias; veja a aba Actions do GitHub)")
        else:
            print("   OK: os %d pregão(ões) encerrados desde %s estão no diário."
                  % (len(esperados), INICIO.strftime("%d/%m")))
    except Exception as e:  # calendário indisponível não derruba a análise
        print("   Não consegui checar o calendário da B3 (%s)." % e)
    media_dia = statistics.fmean(len([o for o in ops if o["dia"] == d]) for d in dias)
    if len(oh) < 0.5 * media_dia:
        print("   ATENÇÃO: o último pregão teve bem menos sinais que a média (%d x %.0f). Pode ser falha nos dados."
              % (len(oh), media_dia))

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["data", "operacoes", "acerto_pct", "media_pct", "acumulado_pct"])
        for d, sd, ac in linhas:
            w.writerow([d.isoformat(), sd["n"], ("%.1f" % sd["acerto"]).replace(".", ","),
                        ("%.3f" % sd["media"]).replace(".", ","), ("%.3f" % ac).replace(".", ",")])
    print("\nPlanilha por dia: analise/por_dia.csv. Não é recomendação de investimento.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
