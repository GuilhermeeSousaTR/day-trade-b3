#!/usr/bin/env python3
"""Robô de treino: opera o rompimento da faixa de abertura (ORB) SÓ NA CONTA DEMO do MetaTrader 5.

Para que serve: aprender a execução de verdade (ordens, escorregamento de preço, stops) com
dinheiro de mentira, e comparar o resultado real das ordens com o diário teórico.
A regra ORB NÃO tem vantagem comprovada (veja o README): isto é treino, não estratégia de lucro.

TRAVAS DE SEGURANÇA
  - Recusa qualquer conta que não seja DEMO (confere o tipo da conta E o nome do servidor).
  - Valor fixo por operação, limite de posições, de entradas e de perda no dia.
  - Zera tudo 5 minutos antes do fim do pregão.
  - Para na hora se existir o arquivo PARAR_ROBO.txt nesta pasta (o PARAR_ROBO.bat cria).
  - Só mexe nas posições que ele mesmo abriu (número mágico).

  py -3.14 robo_demo.py verificar     confere tudo SEM enviar ordem
  py -3.14 robo_demo.py               opera o pregão de hoje até o fechamento

Registros em robo_demo/: operacoes.csv (todas as operações) e AAAA-MM-DD.txt (log do dia).
Não é recomendação de investimento.
"""
import csv
import datetime as dt
import importlib.util
import math
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
PASTA = os.path.join(AQUI, "robo_demo")
PARAR = os.path.join(AQUI, "PARAR_ROBO.txt")

# ---------------------------------------------------------------- configuração (dinheiro de mentira)
VALOR_POR_OPERACAO = 10000.0   # R$ por operação
MAX_POSICOES = 10              # posições abertas ao mesmo tempo
MAX_ENTRADAS_DIA = 20          # entradas por dia
PERDA_MAXIMA_DIA = 3000.0      # R$: se a perda do dia chegar aqui, zera tudo e para de entrar
ALVO_R = 1.0                   # alvo = 1x o risco (igual ao diário)
MAGIC = 26112024               # marca as ordens deste robô
DESVIO = 20                    # desvio máximo de preço aceito, em pontos

CAMPOS = ["data", "acao", "hora_sinal", "preco_sinal", "hora_entrada", "preco_entrada", "quantidade",
          "stop", "alvo", "hora_saida", "preco_saida", "motivo_saida", "resultado_pct", "resultado_reais",
          "escorregamento_entrada_pct"]


# ---------------------------------------------------------------- relógio (trocável nos testes)
def agora_brasilia():
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - dt.timedelta(hours=3)


def dormir(seg):
    time.sleep(seg)


# ---------------------------------------------------------------- utilidades
def _modulo(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sessao_hoje(d):
    return _modulo("b3exit", os.path.join(AQUI, "trader-exit", "exit.py")).session(d)


def lista_acoes():
    with open(os.path.join(AQUI, "trader", "universe.txt"), encoding="utf-8") as fh:
        return [ln.split("|")[0].strip() for ln in fh if ln.strip() and not ln.startswith("#")]


class Log:
    def __init__(self, dia):
        os.makedirs(PASTA, exist_ok=True)
        self.arq = os.path.join(PASTA, dia.isoformat() + ".txt")

    def __call__(self, msg):
        linha = "%s  %s" % (agora_brasilia().strftime("%H:%M:%S"), msg)
        print(linha, flush=True)
        with open(self.arq, "a", encoding="utf-8") as fh:
            fh.write(linha + "\n")


def registrar(op):
    os.makedirs(PASTA, exist_ok=True)
    arq = os.path.join(PASTA, "operacoes.csv")
    novo = not os.path.exists(arq)
    with open(arq, "a", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";")
        if novo:
            w.writerow(CAMPOS)
        w.writerow([str(op.get(c, "")).replace(".", ",") if isinstance(op.get(c), float) else op.get(c, "")
                    for c in CAMPOS])


# ---------------------------------------------------------------- MetaTrader
def conectar():
    try:
        import MetaTrader5 as mt5
    except ImportError:
        sys.exit("Falta o pacote MetaTrader5 (py -3.14 -m pip install MetaTrader5).")
    if not mt5.initialize():
        sys.exit("Não consegui abrir o MetaTrader 5 (%s). Abra o programa e entre na conta demo." % (mt5.last_error(),))
    return mt5


def checar_conta(mt5):
    """Devolve a conta se for DEMO; senão encerra. Nunca opera conta real."""
    conta = mt5.account_info()
    if conta is None:
        mt5.shutdown()
        sys.exit("MetaTrader aberto, mas sem conta conectada. Entre na conta DEMO (Simulador).")
    demo_tipo = conta.trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
    demo_nome = "DEMO" in str(conta.server).upper()
    if not (demo_tipo and demo_nome):
        mt5.shutdown()
        sys.exit("PAREI: a conta conectada NÃO é demo (servidor %s). Este robô só opera conta DEMO, "
                 "com dinheiro de mentira." % conta.server)
    return conta


def fuso(mt5, simbolos):
    """Horas a somar ao horário do servidor para chegar ao UTC (pela 1ª barra de cada dia = 10h)."""
    ponte = _modulo("mt5_ponte", os.path.join(AQUI, "mt5_ponte.py"))
    for s in simbolos[:5]:
        r = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_M5, 0, 2000)
        if r is not None and len(r):
            return ponte.detectar_fuso(r)
    return 3


def barras_hoje(mt5, sym, ajuste, hoje):
    """Barras de 5 min de hoje: lista de (inicio_brasilia, o, h, l, c), da mais antiga para a mais nova."""
    r = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 130)
    if r is None:
        return []
    out = []
    for b in r:
        t = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=int(b["time"]) + (ajuste - 3) * 3600)
        if t.date() == hoje:
            out.append((t, float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])))
    return sorted(out)


def arred(preco, passo):
    return round(round(preco / passo) * passo, 6) if passo else round(preco, 2)


def tipos_preenchimento(mt5, info):
    ordem = [mt5.ORDER_FILLING_RETURN, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK]
    flags = getattr(info, "filling_mode", 0) or 0
    pref = []
    if flags & 2:
        pref.append(mt5.ORDER_FILLING_IOC)
    if flags & 1:
        pref.append(mt5.ORDER_FILLING_FOK)
    return [mt5.ORDER_FILLING_RETURN] + [x for x in pref if x != mt5.ORDER_FILLING_RETURN] + \
        [x for x in ordem if x not in pref and x != mt5.ORDER_FILLING_RETURN]


def enviar(mt5, req, info, log):
    """Envia a ordem testando os tipos de preenchimento aceitos. Devolve o resultado ou None."""
    for f in tipos_preenchimento(mt5, info):
        req["type_filling"] = f
        r = mt5.order_send(req)
        if r is None:
            log("  ordem recusada pelo terminal: %s" % (mt5.last_error(),))
            return None
        if r.retcode == mt5.TRADE_RETCODE_INVALID_FILL:
            continue
        return r
    return None


def quantidade(info, preco):
    passo = info.volume_step or 100
    minimo = info.volume_min or passo
    q = math.floor(VALOR_POR_OPERACAO / preco / passo) * passo
    if q < minimo:
        q = minimo if minimo * preco <= 2.5 * VALOR_POR_OPERACAO else 0
    return float(q)


# ---------------------------------------------------------------- o robô
class Robo:
    def __init__(self, mt5, log, hoje, abertura, fim):
        self.mt5, self.log, self.hoje = mt5, log, hoje
        self.fim = dt.datetime.combine(hoje, fim)
        self.lim_entrada = self.fim - dt.timedelta(minutes=30)
        self.lim_saida = self.fim - dt.timedelta(minutes=5)
        self.abertura = dt.datetime.combine(hoje, abertura)
        self.ja_operou = set()        # cada ação no máximo 1 vez por dia (igual ao diário)
        self.abertas = {}             # ticket -> dados da operação
        self.entradas = 0
        self.resultado_dia = 0.0
        self.bloqueado = False
        self.encerradas = []

    # ---------- entrada
    def procurar_sinais(self, simbolos, ajuste, agora):
        mt5 = self.mt5
        if agora >= self.lim_entrada or self.bloqueado:
            return
        for sym in simbolos:
            if sym in self.ja_operou:
                continue
            b = barras_hoje(mt5, sym, ajuste, self.hoje)
            fechadas = [x for x in b if x[0] + dt.timedelta(minutes=5) <= agora]
            horas = {x[0].time(): x for x in fechadas}
            faixa = [horas.get(dt.time(10, m)) for m in (0, 5, 10)]
            if None in faixa:
                continue
            maxf, minf = max(x[2] for x in faixa), min(x[3] for x in faixa)
            rompeu = None
            for x in fechadas:
                if x[0].time() >= dt.time(10, 15) and x[0] + dt.timedelta(minutes=5) <= self.lim_entrada and x[4] > maxf:
                    rompeu = x
                    break
            if not rompeu:
                continue
            self.ja_operou.add(sym)
            fim_barra = rompeu[0] + dt.timedelta(minutes=5)
            if agora - fim_barra > dt.timedelta(minutes=2):
                self.log("%s: rompeu às %s, antes de o robô estar olhando; não entra (seria preço velho)."
                         % (sym, fim_barra.strftime("%H:%M")))
                continue
            if len(self.abertas) >= MAX_POSICOES or self.entradas >= MAX_ENTRADAS_DIA:
                self.log("%s: sinal às %s, mas o limite de %s está cheio; não entra."
                         % (sym, fim_barra.strftime("%H:%M"),
                            "posições abertas" if len(self.abertas) >= MAX_POSICOES else "entradas do dia"))
                continue
            if mt5.positions_get(symbol=sym):
                self.log("%s: já existe posição nesta ação (aberta fora do robô); não entra." % sym)
                continue
            self.comprar(sym, rompeu[4], fim_barra, (maxf + minf) / 2)

    def comprar(self, sym, preco_sinal, hora_sinal, stop):
        mt5 = self.mt5
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None or not tick.ask:
            self.log("%s: sem cotação agora; não entra." % sym)
            return
        preco = tick.ask
        risco = preco - stop
        if risco <= 0:
            self.log("%s: preço já abaixo do stop; não entra." % sym)
            return
        q = quantidade(info, preco)
        if q <= 0:
            self.log("%s: lote mínimo caro demais para R$ %.0f; não entra." % (sym, VALOR_POR_OPERACAO))
            return
        passo = getattr(info, "trade_tick_size", 0.01) or 0.01
        sl, tp = arred(stop, passo), arred(preco + ALVO_R * risco, passo)
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sym, "volume": q, "type": mt5.ORDER_TYPE_BUY,
               "price": preco, "sl": sl, "tp": tp, "deviation": DESVIO, "magic": MAGIC,
               "comment": "ORB demo", "type_time": mt5.ORDER_TIME_DAY}
        r = enviar(mt5, req, info, self.log)
        if r is not None and r.retcode == mt5.TRADE_RETCODE_INVALID_STOPS:
            self.log("%s: corretora não aceitou stop/alvo junto; o robô vai controlar os dois." % sym)
            req["sl"], req["tp"] = 0.0, 0.0
            r = enviar(mt5, req, info, self.log)
        if r is None or r.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
            self.log("%s: compra NÃO executada (código %s: %s)." % (sym, getattr(r, "retcode", "?"),
                                                                    getattr(r, "comment", "")))
            return
        exec_preco = r.price or preco
        pos = [p for p in (mt5.positions_get(symbol=sym) or []) if p.magic == MAGIC]
        ticket = pos[0].ticket if pos else r.order
        self.entradas += 1
        self.abertas[ticket] = {"data": self.hoje.isoformat(), "acao": sym, "hora_sinal": hora_sinal.strftime("%H:%M"),
                                "preco_sinal": round(preco_sinal, 2), "hora_entrada": agora_brasilia().strftime("%H:%M:%S"),
                                "preco_entrada": round(exec_preco, 2), "quantidade": int(q), "stop": sl, "alvo": tp,
                                "escorregamento_entrada_pct": round(100 * (exec_preco / preco_sinal - 1), 3),
                                "ticket": ticket, "volume": q}
        self.log("COMPROU %s: %d ações a %.2f (sinal %.2f) | stop %.2f | alvo %.2f"
                 % (sym, q, exec_preco, preco_sinal, sl, tp))

    # ---------- saída
    def fechar(self, ticket, motivo):
        mt5 = self.mt5
        op = self.abertas.get(ticket)
        pos = [p for p in (mt5.positions_get(ticket=ticket) or [])]
        if not op or not pos:
            return
        p = pos[0]
        info = mt5.symbol_info(op["acao"])
        tick = mt5.symbol_info_tick(op["acao"])
        if tick is None or not tick.bid:
            self.log("%s: sem cotação para sair agora; tento de novo em seguida." % op["acao"])
            return
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": op["acao"], "volume": p.volume,
               "type": mt5.ORDER_TYPE_SELL, "position": ticket, "price": tick.bid, "deviation": DESVIO,
               "magic": MAGIC, "comment": "ORB demo saida", "type_time": mt5.ORDER_TIME_DAY}
        r = enviar(mt5, req, info, self.log)
        if r is None or r.retcode not in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED):
            self.log("%s: venda para sair NÃO executada (código %s). Vou tentar de novo."
                     % (op["acao"], getattr(r, "retcode", "?")))
            return
        self.encerrar(ticket, r.price or tick.bid, motivo)

    def encerrar(self, ticket, preco_saida, motivo):
        op = self.abertas.pop(ticket)
        op["hora_saida"] = agora_brasilia().strftime("%H:%M:%S")
        op["preco_saida"] = round(preco_saida, 2)
        op["motivo_saida"] = motivo
        op["resultado_pct"] = round(100 * (preco_saida / op["preco_entrada"] - 1), 3)
        op["resultado_reais"] = round((preco_saida - op["preco_entrada"]) * op["volume"], 2)
        self.resultado_dia += op["resultado_reais"]
        registrar(op)
        self.encerradas.append(op)
        self.log("SAIU %s (%s) a %.2f: %+.2f%% | R$ %+.2f | resultado do dia R$ %+.2f"
                 % (op["acao"], motivo, preco_saida, op["resultado_pct"], op["resultado_reais"], self.resultado_dia))

    def vigiar(self, agora):
        mt5 = self.mt5
        for ticket in list(self.abertas):
            op = self.abertas[ticket]
            pos = mt5.positions_get(ticket=ticket)
            if pos is None:  # falha momentânea de comunicação: não conclui nada, tenta no próximo ciclo
                continue
            if not pos:  # a corretora já executou o stop ou o alvo
                deals = mt5.history_deals_get(position=ticket) or []
                saida = [d for d in deals if d.entry == getattr(mt5, "DEAL_ENTRY_OUT", 1)]
                preco = saida[-1].price if saida else op["preco_entrada"]
                motivo = "stop" if preco <= op["stop"] + 1e-9 else ("alvo" if preco >= op["alvo"] - 1e-9 else "corretora")
                self.encerrar(ticket, preco, motivo)
                continue
            tick = mt5.symbol_info_tick(op["acao"])
            if tick and tick.bid:
                if op["stop"] and tick.bid <= op["stop"]:
                    self.fechar(ticket, "stop")
                elif op["alvo"] and tick.bid >= op["alvo"]:
                    self.fechar(ticket, "alvo")
        flutuante = sum((p.profit or 0) for p in (mt5.positions_get() or []) if p.magic == MAGIC)
        if not self.bloqueado and self.resultado_dia + flutuante <= -PERDA_MAXIMA_DIA:
            self.bloqueado = True
            self.log("LIMITE DE PERDA DO DIA (R$ %.0f) atingido: zerando tudo e sem novas entradas." % PERDA_MAXIMA_DIA)
            self.fechar_tudo("limite de perda do dia")

    def fechar_tudo(self, motivo):
        for ticket in list(self.abertas):
            self.fechar(ticket, motivo)
        self.varrer_esquecidas(motivo)

    def varrer_esquecidas(self, motivo):
        """Zera posições deste robô que ele não está acompanhando (ex.: sobra de um dia em que travou)."""
        mt5 = self.mt5
        for p in (mt5.positions_get() or []):
            if p.magic != MAGIC or p.ticket in self.abertas:
                continue
            tick = mt5.symbol_info_tick(p.symbol)
            if tick is None or not tick.bid:
                continue
            req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                   "type": mt5.ORDER_TYPE_SELL, "position": p.ticket, "price": tick.bid, "deviation": DESVIO,
                   "magic": MAGIC, "comment": "ORB demo limpeza", "type_time": mt5.ORDER_TIME_DAY}
            r = enviar(mt5, req, mt5.symbol_info(p.symbol), self.log)
            ok = r is not None and r.retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED)
            self.log("%s: posição do robô que estava sem acompanhamento %s (%s)."
                     % (p.symbol, "ZERADA" if ok else "NÃO zerada, tento de novo", motivo))

    def resumo(self):
        ops = self.encerradas
        linhas = ["", "RESUMO DO DIA %s (conta demo, dinheiro de mentira)" % self.hoje.strftime("%d/%m/%Y")]
        if not ops:
            linhas.append("Nenhuma operação hoje.")
        else:
            ganhos = sum(1 for o in ops if o["resultado_reais"] > 0)
            esc = sum(o["escorregamento_entrada_pct"] for o in ops) / len(ops)
            linhas.append("Operações: %d | acertos: %d (%.0f%%) | resultado: R$ %+.2f"
                          % (len(ops), ganhos, 100 * ganhos / len(ops), self.resultado_dia))
            linhas.append("Escorregamento médio na entrada: %+.3f%% (quanto o preço executado ficou acima do sinal;"
                          " o teste assume 0,10%% de custo total)" % esc)
        linhas.append("Não é recomendação de investimento.")
        for ln in linhas:
            self.log(ln)


_TRAVA = []


def travar_unico():
    """Garante um robô só por vez (o agendado e o do menu não podem operar juntos)."""
    os.makedirs(PASTA, exist_ok=True)
    f = open(os.path.join(PASTA, "robo.trava"), "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _TRAVA.append(f)
    return True


def pediu_parada():
    """PARAR_ROBO.txt só vale no dia em que foi criado (não trava o robô nos dias seguintes)."""
    if not os.path.exists(PARAR):
        return False
    criado = dt.datetime.fromtimestamp(os.path.getmtime(PARAR)).date()
    return criado == agora_brasilia().date()


def rodar():
    hoje = agora_brasilia().date()
    log = Log(hoje)
    s = sessao_hoje(hoje)
    if not s:
        log("Hoje não tem pregão na B3. Até o próximo.")
        return 0
    if not travar_unico():
        log("Já existe um robô rodando (outra janela ou o agendado). Este não vai operar.")
        return 1
    mt5 = conectar()
    conta = checar_conta(mt5)
    term = mt5.terminal_info()
    if term is not None and not getattr(term, "trade_allowed", True):
        mt5.shutdown()
        log("O botão 'Algo Trading' do MetaTrader está desligado. Clique nele (fica verde) e rode de novo.")
        return 1
    simbolos = [x for x in lista_acoes() if mt5.symbol_select(x, True)]
    ajuste = fuso(mt5, simbolos)
    robo = Robo(mt5, log, hoje, s[0], s[1])
    robo.varrer_esquecidas("sobra de antes")
    log("Robô de TREINO ligado | conta DEMO %s | servidor %s | %d ações | R$ %.0f por operação | "
        "zera às %s" % (conta.login, conta.server, len(simbolos), VALOR_POR_OPERACAO,
                        robo.lim_saida.strftime("%H:%M")))
    ultimo_ciclo = None
    while True:
        agora = agora_brasilia()
        try:
            if pediu_parada():
                log("Arquivo PARAR_ROBO.txt de hoje encontrado: zerando tudo e desligando.")
                robo.fechar_tudo("parado pelo usuário")
                break
            robo.vigiar(agora)
            if agora >= robo.lim_saida:
                robo.fechar_tudo("fim do pregão")
                if not robo.abertas or agora >= robo.fim:
                    break
            elif agora >= robo.abertura + dt.timedelta(minutes=20):
                ciclo = agora.replace(second=0, microsecond=0, minute=agora.minute - agora.minute % 5)
                if ciclo != ultimo_ciclo and agora >= ciclo + dt.timedelta(seconds=5):
                    robo.procurar_sinais(simbolos, ajuste, agora)
                    ultimo_ciclo = ciclo
        except Exception as e:  # um erro num ciclo não pode deixar posição aberta sem vigia
            log("Erro inesperado (%s: %s); sigo vigiando." % (type(e).__name__, e))
        dormir(10)
    robo.resumo()
    mt5.shutdown()
    return 0


def verificar():
    """Confere tudo sem enviar nenhuma ordem."""
    mt5 = conectar()
    conta = checar_conta(mt5)
    print("Conta DEMO ok: %s | servidor %s | saldo R$ %.2f" % (conta.login, conta.server, conta.balance))
    term = mt5.terminal_info()
    ok_algo = getattr(term, "trade_allowed", False)
    print("Botão 'Algo Trading': %s" % ("LIGADO" if ok_algo else "DESLIGADO (clique nele no MetaTrader antes de rodar)"))
    acoes = lista_acoes()
    disp = [x for x in acoes if mt5.symbol_select(x, True)]
    print("Ações disponíveis: %d de %d" % (len(disp), len(acoes)))
    if disp:
        info = mt5.symbol_info(disp[0])
        tick = mt5.symbol_info_tick(disp[0])
        print("Exemplo %s: lote %s, passo de preço %s, último preço %s"
              % (disp[0], info.volume_step, info.trade_tick_size, getattr(tick, "last", "?")))
        print("Fuso do servidor: UTC%+d" % (-fuso(mt5, disp)))
    s = sessao_hoje(agora_brasilia().date())
    print("Pregão hoje: %s" % ("%s às %s" % (s[0].strftime("%H:%M"), s[1].strftime("%H:%M")) if s else "não tem"))
    print("Configuração: R$ %.0f por operação | até %d posições | até %d entradas | perda máxima no dia R$ %.0f"
          % (VALOR_POR_OPERACAO, MAX_POSICOES, MAX_ENTRADAS_DIA, PERDA_MAXIMA_DIA))
    mt5.shutdown()
    print("Nenhuma ordem foi enviada.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verificar":
        raise SystemExit(verificar())
    raise SystemExit(rodar())
