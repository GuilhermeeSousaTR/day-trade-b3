#!/usr/bin/env python3
"""Sai com código 0 se hoje (horário de Brasília) tem pregão na B3, 1 se não tem."""
import datetime as dt
import importlib.util
import os
import sys

aqui = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("b3exit", os.path.join(aqui, "trader-exit", "exit.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
hoje = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).date()
tem = bool(m.session(hoje))
print("%s: %s" % (hoje.strftime("%d/%m/%Y"), "tem pregão" if tem else "sem pregão na B3"))
sys.exit(0 if tem else 1)
