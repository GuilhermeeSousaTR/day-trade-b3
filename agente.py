#!/usr/bin/env python3
"""Agentes automáticos (rodam sozinhos pelo Agendador de Tarefas do Windows).

  py -3.14 agente.py manha   # dias úteis, 10h45: baixa dados do MetaTrader e faz a varredura
  py -3.14 agente.py noite   # dias úteis, 18h15: baixa dados e atualiza o diário de sinais

Cada execução grava um relatório em relatorios\\AAAA-MM-DD_manha.txt (ou _noite.txt)
e uma linha em relatorios\\historico.log. Só lê dados; NUNCA envia ordens.
Fins de semana e feriados da B3 são pulados.
"""
import datetime as dt
import importlib.util
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA_REL = os.path.join(AQUI, "relatorios")


def agora_brasilia():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)


def tem_pregao(d):
    spec = importlib.util.spec_from_file_location("b3exit", os.path.join(AQUI, "trader-exit", "exit.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return bool(m.session(d))


def rodar(passos, rel):
    linhas = []
    ok = True
    for titulo, cmd in passos:
        linhas.append("=== %s ===" % titulo)
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            p = subprocess.run(cmd, cwd=AQUI, env=env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=900)
            linhas.append((p.stdout or "") + (p.stderr or ""))
            if p.returncode not in (0, 1):  # 1 = "nada a fazer" em várias ferramentas
                ok = False
        except Exception as e:  # noqa: BLE001
            linhas.append("ERRO: %s" % e)
            ok = False
    with open(rel, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas))
    return ok, "\n".join(linhas)


def main():
    modo = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if modo not in ("manha", "noite"):
        raise SystemExit("Uso: agente.py manha | noite")
    os.makedirs(PASTA_REL, exist_ok=True)
    agora = agora_brasilia()
    hist = os.path.join(PASTA_REL, "historico.log")
    if not tem_pregao(agora.date()):
        with open(hist, "a", encoding="utf-8") as fh:
            fh.write("%s %s: sem pregão hoje, nada feito\n" % (agora.strftime("%Y-%m-%d %H:%M"), modo))
        return
    py = sys.executable
    baixar = ("Baixar dados do MetaTrader", [py, "mt5_ponte.py", "baixar", "--lista"])
    rel = os.path.join(PASTA_REL, "%s_%s.txt" % (agora.strftime("%Y-%m-%d"), modo))
    ok1, t1 = rodar([baixar], rel)
    if modo == "manha":
        agora_txt = os.path.join(AQUI, "dados_mt5", "agora.txt")
        ref = (open(agora_txt, encoding="utf-8").read().strip() if os.path.exists(agora_txt)
               else agora.strftime("%Y-%m-%d %H:%M"))
        passo = ("Varredura (rompimento da faixa de abertura)",
                 [py, os.path.join("trader-scanner", "scan.py"), "orb", "--offline",
                  os.path.join("dados_mt5", "varredura_5m.json"), "--now", ref, "--min-price", "1"])
    else:
        passo = ("Diário de sinais", [py, "diario.py"])
    ok2, t2 = rodar([passo], rel)
    ok = ok1 and ok2
    with open(rel, "w", encoding="utf-8") as fh:
        fh.write(t1 + "\n" + t2)
    with open(hist, "a", encoding="utf-8") as fh:
        fh.write("%s %s: %s -> %s\n" % (agora.strftime("%Y-%m-%d %H:%M"), modo,
                                        "ok" if ok else "COM ERRO", os.path.basename(rel)))


if __name__ == "__main__":
    main()
