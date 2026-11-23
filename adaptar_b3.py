#!/usr/bin/env python3
"""Adapta o pacote day-trader-skill (MIT, Jake Schincariol) para a B3.

Uso: python3 adaptar_b3.py <pasta-original> <pasta-destino>
"""
import os
import re
import shutil
import sys

SRC, DST = sys.argv[1], sys.argv[2]

B3_HOLIDAYS = '''NYSE_HOLIDAYS = {  # B3: dias SEM pregão (2026 confirmado em b3.com.br; 2027 previsto, confira)
    "2026-01-01": "Confraternização Universal",
    "2026-02-16": "Carnaval",
    "2026-02-17": "Carnaval",
    "2026-04-03": "Sexta-feira Santa",
    "2026-04-21": "Tiradentes",
    "2026-05-01": "Dia do Trabalho",
    "2026-06-04": "Corpus Christi",
    "2026-09-07": "Independência",
    "2026-10-12": "Nossa Senhora Aparecida",
    "2026-11-02": "Finados",
    "2026-11-20": "Consciência Negra",
    "2026-12-24": "Véspera de Natal",
    "2026-12-25": "Natal",
    "2026-12-31": "Véspera de Ano Novo",
    "2027-01-01": "Confraternização Universal",
    "2027-02-08": "Carnaval (previsto)",
    "2027-02-09": "Carnaval (previsto)",
    "2027-03-26": "Sexta-feira Santa (previsto)",
    "2027-04-21": "Tiradentes (previsto)",
    "2027-05-27": "Corpus Christi (previsto)",
    "2027-09-07": "Independência (previsto)",
    "2027-10-12": "Nossa Senhora Aparecida (previsto)",
    "2027-11-02": "Finados (previsto)",
    "2027-11-15": "Proclamação da República (previsto)",
    "2027-12-24": "Véspera de Natal (previsto)",
    "2027-12-31": "Véspera de Ano Novo (previsto)",
}'''

B3_EARLY = 'NYSE_EARLY_CLOSE = {}  # B3: sem fechamento antecipado; Quarta de Cinzas abre às 13h (B3_LATE_OPEN)'

NEWDEFS = '''def eastern_offset(utc):
    """B3: horário de Brasília, UTC-3 o ano todo (o Brasil não tem horário de verão desde 2019)."""
    return -3


def eastern_to_utc(local):
    import datetime as _b3dt
    return local + _b3dt.timedelta(hours=3)


B3_LATE_OPEN = {"2026-02-18": "Quarta-feira de Cinzas", "2027-02-10": "Quarta-feira de Cinzas (previsto)"}


def _b3_nth_sunday(year, month, n):
    import datetime as _b3dt
    d = _b3dt.date(year, month, 1)
    d += _b3dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + _b3dt.timedelta(weeks=n - 1)


def b3_close(d):
    """Fim do pregão à vista da B3. A B3 acompanha o horário de verão dos EUA:
    10h às 16h55 enquanto Nova York está em horário de verão, 10h às 17h55 fora dele."""
    import datetime as _b3dt
    if isinstance(d, _b3dt.datetime):
        d = d.date()
    dst = _b3_nth_sunday(d.year, 3, 2) < d <= _b3_nth_sunday(d.year, 11, 1)
    return _b3dt.time(16, 55) if dst else _b3dt.time(17, 55)


def b3_open(d):
    import datetime as _b3dt
    if isinstance(d, _b3dt.datetime):
        d = d.date()
    return _b3dt.time(13, 0) if d.isoformat() in B3_LATE_OPEN else _b3dt.time(10, 0)


def b3_yahoo(sym):
    """Código da B3 -> símbolo do Yahoo: PETR4 -> PETR4.SA, PETR4F (fracionário) -> PETR4.SA."""
    import re as _b3re
    s = str(sym).upper().strip()
    if s.endswith(".SA") or s.startswith("^"):
        return s
    m = _b3re.fullmatch(r"([A-Z][A-Z0-9]{3}\\d{1,2})F?", s)
    if m:
        return m.group(1) + ".SA"
    return s.replace(".", "-")


'''

B3_UNIVERSE = [
    ("PETR4", "Petrobras PN"), ("PETR3", "Petrobras ON"), ("VALE3", "Vale"), ("ITUB4", "Itaú Unibanco"),
    ("BBDC4", "Bradesco PN"), ("BBAS3", "Banco do Brasil"), ("B3SA3", "B3"), ("ABEV3", "Ambev"),
    ("WEGE3", "WEG"), ("ITSA4", "Itaúsa"), ("BPAC11", "BTG Pactual"), ("SANB11", "Santander"),
    ("SUZB3", "Suzano"), ("RENT3", "Localiza"), ("RADL3", "Raia Drogasil"), ("EQTL3", "Equatorial"),
    ("RDOR3", "Rede D'Or"), ("PRIO3", "PRIO"), ("GGBR4", "Gerdau"), ("CSNA3", "CSN"),
    ("USIM5", "Usiminas"), ("CMIG4", "Cemig"), ("CPLE6", "Copel"), ("TAEE11", "Taesa"),
    ("EGIE3", "Engie"), ("SBSP3", "Sabesp"), ("CSAN3", "Cosan"), ("RAIL3", "Rumo"),
    ("UGPA3", "Ultrapar"), ("VBBR3", "Vibra"), ("LREN3", "Lojas Renner"), ("MGLU3", "Magazine Luiza"),
    ("ASAI3", "Assaí"), ("HAPV3", "Hapvida"), ("FLRY3", "Fleury"), ("HYPE3", "Hypera"),
    ("TOTS3", "Totvs"), ("EMBR3", "Embraer"), ("KLBN11", "Klabin"), ("BRAP4", "Bradespar"),
    ("CMIN3", "CSN Mineração"), ("GOAU4", "Metalúrgica Gerdau"), ("CYRE3", "Cyrela"), ("MRVE3", "MRV"),
    ("EZTC3", "EZTec"), ("MULT3", "Multiplan"), ("BBSE3", "BB Seguridade"), ("CXSE3", "Caixa Seguridade"),
    ("PSSA3", "Porto Seguro"), ("IRBR3", "IRB"), ("COGN3", "Cogna"), ("YDUQ3", "Yduqs"),
    ("ALOS3", "Allos"), ("SLCE3", "SLC Agrícola"), ("SMTO3", "São Martinho"), ("VIVT3", "Vivo"),
    ("TIMS3", "TIM"), ("ENEV3", "Eneva"), ("ENGI11", "Energisa"), ("CPFE3", "CPFL"),
    ("NEOE3", "Neoenergia"), ("ALUP11", "Alupar"), ("SAPR11", "Sanepar"), ("CSMG3", "Copasa"),
    ("BRKM5", "Braskem"), ("UNIP6", "Unipar"), ("RECV3", "PetroReconcavo"), ("BRAV3", "Brava"),
    ("PETZ3", "Petz"), ("VAMO3", "Vamos"), ("SMFT3", "Smart Fit"), ("AURE3", "Auren"),
    ("DIRR3", "Direcional"), ("CVCB3", "CVC"), ("POMO4", "Marcopolo"), ("RAPT4", "Randon"),
    ("STBP3", "Santos Brasil"), ("MOTV3", "Motiva"), ("MBRF3", "MBRF"), ("NATU3", "Natura"),
    ("AZZA3", "Azzas 2154"), ("BEEF3", "Minerva"), ("INTB3", "Intelbras"), ("LWSA3", "Locaweb"),
    ("ODPV3", "Odontoprev"), ("SIMH3", "Simpar"), ("TEND3", "Tenda"), ("CURY3", "Cury"),
]

TEXT = [  # textos e padrões americanos -> B3
    ("New York", "Brasília"), ("NYSE", "B3"), ("nyse.com", "b3.com.br"),
    ("the 1:00 p.m. early close", "o pregão mais curto (horário de verão dos EUA, até 16h55)"),
    ("1:00 p.m. early close", "pregão mais curto (horário de verão dos EUA)"),
]


def patch_common(s, name):
    s = re.sub(r"NYSE_HOLIDAYS = \{.*?\n\}", lambda m: B3_HOLIDAYS, s, flags=re.S)
    s = re.sub(r"NYSE_EARLY_CLOSE = \{.*?\n\}", lambda m: B3_EARLY, s, flags=re.S)
    s = s.replace("OPEN = datetime.time(9, 30)", "OPEN = datetime.time(10, 0)")
    s = s.replace("CLOSE = datetime.time(16, 0)", "CLOSE = datetime.time(17, 55)")
    if "def eastern_offset(utc):" in s:
        s = s.replace("def eastern_to_utc(local):", "def _ny_to_utc_original(local):", 1)
        s = s.replace("def eastern_offset(utc):", NEWDEFS + "def _ny_offset_original(utc):", 1)
    # sessão: abre 10h (13h na Quarta de Cinzas), fecha 16h55 ou 17h55 conforme o horário de verão dos EUA
    s = s.replace("return OPEN, (EARLY if d.isoformat() in NYSE_EARLY_CLOSE else CLOSE)",
                  "return b3_open(d), b3_close(d)")
    # símbolos do Yahoo
    s = re.sub(r"(\w+)\.upper\(\)\.replace\(\"\.\", \"-\"\)", r"b3_yahoo(\1)", s)
    s = s.replace('ysym.upper().replace("-", ".")', 'ysym.upper().replace("-", ".").replace(".SA", "")')
    s = re.sub(r'"%s 09:30" % (\w+)\.isoformat\(\)',
               r'"%s %s" % (\1.isoformat(), b3_open(\1).strftime("%H:%M"))', s)
    # horários-padrão (o código já recua tudo 1 hora quando o pregão fecha às 16h55)
    for a, b in [('"15:55"', '"17:50"'), ('"15:30"', '"17:25"'), ('"09:45"', '"10:15"'),
                 ('"%s 09:30"', '"%s 10:00"'), ("15:55", "17:50"), ("9:30", "10:00")]:
        s = s.replace(a, b)
    for a, b in TEXT:
        s = s.replace(a, b)
    for a in ('"', " ", ")", ":", ","):  # rótulo de fuso nos textos (não toca no módulo xml "ET.")
        s = s.replace(" ET" + a, " BRT" + a)
    s = s.replace('"source": "Yahoo Finance", "kind": "headline"', '"source": "Google Notícias", "kind": "headline"')
    return s


def patch_risk(s):
    s = s.replace('TICKER = re.compile(r"^[A-Z]{1,5}([.\\-][A-Z]{1,2})?$")',
                  'TICKER = re.compile(r"^[A-Z][A-Z0-9]{3}\\d{1,2}F?$")  # B3: PETR4, TAEE11, PETR4F, BDRs (AAPL34)')
    s = s.replace("does not look like a US stock or ETF ticker", "não parece um código de ação da B3 (ex.: PETR4)")
    s = s.replace("close = EARLY if d.isoformat() in NYSE_EARLY_CLOSE else CLOSE", "close = b3_close(d)")
    s = s.replace("if t < OPEN or now_et.time() >= close:", "if t < b3_open(d) or now_et.time() >= close:")
    s = s.replace("if close == EARLY and", "if close != CLOSE and")
    return s


def patch_timemachine(s):
    # janela comum aos dois horários da B3: 10h00 a 16h55 (83 barras de 5 min)
    s = s.replace("SESSION_BARS = 78    # 9:30 to 16:00 in 5-minute bars",
                  "SESSION_BARS = 83    # B3: 10:00 a 16:55 (parte comum aos dois horários do ano)")
    s = s.replace("OPEN_MIN = 9 * 60 + 30", "OPEN_MIN = 10 * 60")
    s = s.replace("CLOSE_MIN = 16 * 60", "CLOSE_MIN = 16 * 60 + 55")
    s = s.replace("if len(s) == SESSION_BARS:", "if all(i in s for i in range(SESSION_BARS)):")
    s = s.replace('t = mc.get("until") or "16:00"', 't = mc.get("until") or "16:55"')
    s = s.replace("15:55", "16:50")  # simulação vai no máximo até 16h55
    s = s.replace("or_min >= 390", "or_min >= SESSION_BARS * 5")
    # B3: sem --date e sem pregão hoje (fim de semana, feriado, antes da abertura) -> usa o último pregão dos dados
    s = s.replace('''    entry_day = days.get(plan["date"], {})
    if k not in entry_day:''', '''    entry_day = days.get(plan["date"], {})
    if k not in entry_day and plan["date"] == to_eastern(now_utc).date().isoformat():
        prev = [d for d in sorted(days) if d < plan["date"] and k in days[d]]
        if prev:
            plan["date"] = prev[-1]
            entry_day = days[prev[-1]]
    if k not in entry_day:''')
    s = s.replace("(default 16:00, the close)", "(padrão 16:55)")
    s = s.replace('if msym and msym != sym.replace(".", "-"):',
                  'if msym and msym.replace(".SA", "") != b3_yahoo(sym).replace(".SA", ""):')
    s = s.replace('"data": {"symbol": msym or sym,', '"data": {"symbol": (msym or sym).replace(".SA", ""),')
    return s


def patch_entry(s):
    s = s.replace('return {"symbol": str(meta.get("symbol") or sym).upper(),',
                  'return {"symbol": str(meta.get("symbol") or sym).upper().replace(".SA", ""),')
    s = s.replace('if ch["symbol"] != yahoo_symbol(sym):',
                  'if ch["symbol"] != yahoo_symbol(sym).replace(".SA", ""):')
    return s


def patch_scanner(s):
    uni = "B3_UNIVERSE = [\n" + "".join('    (%r, %r),\n' % p for p in B3_UNIVERSE) + "]\n\n\n"
    s = s.replace("def cmd_universe(a):", uni + "def _cmd_universe_nasdaq(a):", 1)
    s = s.replace("def _cmd_universe_nasdaq(a):", '''def cmd_universe(a):
    """B3: grava uma lista de partida de ações líquidas da B3 (edite o arquivo à vontade).
    Códigos que o Yahoo não conhece são simplesmente ignorados na varredura."""
    if not a.no_write:
        d = os.path.dirname(a.out)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            for sym, name in B3_UNIVERSE:
                fh.write("%s|%s\\n" % (sym, name))
    print("Lista da B3 gravada: %d ações em %s. Edite o arquivo para incluir ou tirar ações."
          % (len(B3_UNIVERSE), None if a.no_write else a.out))


def _cmd_universe_nasdaq(a):''', 1)
    return s


def patch_news(s):
    s = s.replace('YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=US&lang=en-US"',
                  'YAHOO = "https://news.google.com/rss/search?q=%s+a%%C3%%A7%%C3%%B5es&hl=pt-BR&gl=BR&ceid=BR:pt-419"'
                  '  # B3: Google Notícias em português')
    s = s.replace("YAHOO % yahoo_symbol(t)", "YAHOO % t.upper()")
    return s


EXTRA = {"trader-risk/check.py": patch_risk, "trader-timemachine/timemachine.py": patch_timemachine,
         "trader-scanner/scan.py": patch_scanner, "trader-news/news.py": patch_news, "trader-entry/entry.py": patch_entry}
SKIP = {"trader-analyst/facts.py", "trader-pelosi/ptr.py"}  # só empresas americanas (úteis para BDRs)

if os.path.exists(DST):
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns(".git", "tests", ".claude-plugin"))
_leia = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LEIA-ME.txt")
for _extra in ("LEIA-ME.txt", "mt5_ponte.py"):
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), _extra)
    if os.path.exists(_p):
        shutil.copy(_p, DST)
for root, _, files in os.walk(DST):
    for f in files:
        if not f.endswith(".py"):
            continue
        p = os.path.join(root, f)
        rel = os.path.relpath(p, DST).replace(os.sep, "/")
        if rel in SKIP:
            continue
        s = open(p, encoding="utf-8").read()
        if rel in EXTRA:
            s = EXTRA[rel](s)  # antes dos textos comuns
        s = patch_common(s, rel)
        open(p, "w", encoding="utf-8").write(s)
        print("adaptado:", rel)


# ---------------------------------------------------------------- SKILL.md
COMUM = """
## Versão B3 (leia antes de tudo; vale sobre o texto em inglês abaixo)

Adaptação para a B3 do pacote day-trader-skill (licença MIT, Jake Schincariol), que foi
feito para a bolsa americana. Quando o texto original divergir destas regras, valem estas:

- Responda sempre em português simples: o usuário é iniciante.
- Horário de Brasília (UTC-3). Pregão à vista da B3: 10h às 17h55 quando os EUA estão fora
  do horário de verão (de novembro a março) e 10h às 16h55 quando estão dentro (de março a
  novembro). Os scripts calculam isso sozinhos. Feriados de 2026 conferidos no site da B3;
  os de 2027 são previsão: confira em b3.com.br.
- Códigos da B3: PETR4, VALE3, TAEE11. Os scripts acrescentam ".SA" para o Yahoo. Lote
  padrão de 100 ações; de 1 a 99 ações a ordem vai no fracionário (código com F, ex.: PETR4F).
- Os scripts imprimem "$", mas na B3 tudo está em reais: mostre sempre em R$. A chave de
  configuração `max_loss_per_trade_usd` vale em reais.
- Dados gratuitos do Yahoo, com atraso (cerca de 15 minutos na B3). Não servem para decidir
  em tempo real.
- Day trade no Brasil paga Imposto de Renda sobre o lucro, com uma parte retida na fonte, além
  de corretagem e emolumentos. Antes de citar alíquotas ou valores, confira as regras atuais
  na Receita Federal.
- Honestidade: mostre sempre a chance de perder junto com a de ganhar. No exemplo do próprio
  autor do pacote, a regra deu praticamente cara ou coroa, e a maioria das pessoas físicas que
  insiste no day trade perde dinheiro. Nunca diga "pode comprar" e nunca prometa lucro.
- Nenhuma ordem real: esta versão não se conecta a corretora brasileira. Antes de usar dinheiro
  de verdade, sugira treinar no simulador de carteira por pelo menos 3 meses.
- Termine com: "Não sou consultor financeiro; isto não é recomendação de investimento."
"""

EXTRA_MD = {
    "trader-timemachine": "- A simulação usa só a parte do pregão comum aos dois horários do ano (10h às 16h55). "
                          "Operações depois das 16h55 não são simuladas.\n",
    "trader-scanner": "- `scan.py universe` grava uma lista de partida com cerca de 90 ações líquidas da B3 em "
                      "trader/universe.txt. Alguns códigos podem ter mudado: o Yahoo ignora os que não conhece. "
                      "Edite o arquivo para incluir ou tirar ações.\n",
    "trader-news": "- Manchetes do Google Notícias em português. A parte da SEC (formulário 8-K) é só para "
                   "empresas americanas: use `--no-sec`. Para fatos relevantes oficiais, indique o site da CVM "
                   "ou de Relações com Investidores da empresa.\n",
    "trader-broker": "- **Na B3 este pacote NÃO envia ordens.** A integração com a Alpaca é americana e não deve "
                     "ser configurada. Use `ticket.py` só para registrar a ordem que o próprio usuário decidir "
                     "digitar no app do banco ou da corretora, depois de passar pelo trader-risk.\n",
    "trader-analyst": "- Só funciona com empresas americanas (dados da SEC). Na B3 serve apenas para BDRs "
                      "(ex.: AAPL34 -> AAPL).\n",
    "trader-pelosi": "- Só cobre políticos dos EUA e empresas americanas. Na B3 serve apenas para BDRs. As "
                     "divulgações chegam com até 45 dias de atraso: trate como curiosidade, nunca como sinal.\n",
    "trader-budget": "- Considere o lote: abaixo de 100 ações a ordem vai no mercado fracionário (código com F).\n",
    "trader-risk": "- O risco aceita códigos da B3 (PETR4, TAEE11, PETR4F) e BDRs (AAPL34).\n",
}

for skill in sorted(os.listdir(DST)):
    md = os.path.join(DST, skill, "SKILL.md")
    if not os.path.exists(md):
        continue
    s = open(md, encoding="utf-8").read()
    s = s.replace("description: >-\n", "description: >-\n  Versão B3 (bolsa brasileira).\n", 1)
    if skill == "trader-broker":
        s = re.sub(r"description: >-\n.*?\nargument-hint", "description: >-\n  Versão B3 (bolsa brasileira). Registro de ordens SEM execução: monta o\n"
                   "  ticket da ordem que o próprio usuário vai digitar no app do banco ou da corretora,\n"
                   "  depois do trader-risk, e anota o resultado. Nunca envia ordens nem configura\n"
                   "  corretora. Use quando o usuário disser \"registrar ordem\", \"anotar compra\",\n"
                   "  \"ticket\" ou depois que o /trader-risk aprovar.\nargument-hint", s, count=1, flags=re.S)
    if skill == "trader-timemachine":
        s = s.replace("16:00", "16:55").replace("15:55", "16:50").replace("4:00 PM", "16:55")
    for a, b in TEXT + [("9:30", "10:00"), ("15:55", "17:50"), ("4:00 PM", "17:55"), ("16:00", "17:55")]:
        s = s.replace(a, b)
    head_end = s.index("\n---\n", 4) + 5
    s = s[:head_end] + COMUM + EXTRA_MD.get(skill, "") + s[head_end:]
    open(md, "w", encoding="utf-8").write(s)
    print("instruções B3:", skill)
