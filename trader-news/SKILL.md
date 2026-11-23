---
name: trader-news
description: >-
  Versão B3 (bolsa brasileira).
  News Monitor. Tracks breaking news on every stock you watch and flags what
  moves it: Yahoo Finance headlines per ticker, each company's 8-K filings on
  SEC EDGAR (earnings, CEO changes, deals, restatements, bankruptcy) and how
  far each stock is from yesterday's close. Shows only what is new since the
  last check, newest first, in Brasília time, tags each item (earnings,
  analyst, deal, halt, regulatory, macro...) and never repeats one. Use when
  the user says "any news on TSLA", "why is this moving", "what's the news on
  my watchlist", "morning briefing", "pre-market news", "monitor the news",
  "did anything break", "check the 8-Ks", or after /trader-scanner finds setups.
argument-hint: "[tickers]"
---

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
- Manchetes do Google Notícias em português. A parte da SEC (formulário 8-K) é só para empresas americanas: use `--no-sec`. Para fatos relevantes oficiais, indique o site da CVM ou de Relações com Investidores da empresa.

# trader-news

A chart can look perfect and still be about to gap on an earnings date, a
halt or a lawsuit. Before a setup becomes a trade, this skill reads the two
feeds that carry those first, for every stock on the watchlist, and tells you
only what is new. It also prints how far each stock has moved today, so a
headline and a move sit side by side.

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                         # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers TSLA NVDA --hours 12
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-sec --json
```

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-scanner) |
| `trader/plan.json` | the trade you are planning (trader-exit) |
| `trader/portfolio.json` | what you hold (trader-broker records fills there) |
| Yahoo Finance headline RSS | `https://feeds.finance.yahoo.com/rss/2.0/headline?s=TSLA&region=US&lang=en-US` |
| Yahoo Finance chart endpoint | the last price against yesterday's close (unofficial, can lag) |
| SEC EDGAR company Atom feed | 8-K by default (`--forms 8-K,10-Q` for more); needs `sec_user_agent` in `trader/config.json` or `SEC_USER_AGENT`, else filings are skipped with a note |
| `trader/state/news.json` | what has been shown (kept 30 days) and each ticker's CIK |

## The rules

- **Headlines are leads, not facts.** Before telling the user something
  happened, open the story or the filing and read it. Quote the source and
  link it. Never summarise a paywalled story you could not read: say so.
- **Filings beat headlines.** If an 8-K and a headline disagree, the 8-K is
  what the company told the SEC.
- **Say what it touches.** Every item lists the tickers it touches and its
  tags: earnings, analyst, legal, deal, capital, people, risk, halt,
  regulatory, macro. Filings marked `!` carry an important 8-K item: earnings
  results (2.02), an officer change (5.02), an impairment (2.06), a delisting
  notice (3.01), past financials no longer reliable (4.02), bankruptcy (1.03)
  or a cyber incident (1.05).
- **MOVING** marks a stock 3 % or more from yesterday's close (`--move-pct`).
  A move with no headline is worth saying out loud too.
- **No predictions.** Report what was published and how far the price is from
  yesterday's close. Never say what the stock will do next.

## Steps

1. Run the check: `python3 "${CLAUDE_SKILL_DIR}/news.py"`. Exit code 1 means
   nothing new. `--all` shows items already seen, `--json` gives everything
   machine readable, `--dry-run` leaves the state alone.
2. Read the items that matter: every `!` filing, anything tagged earnings,
   halt, legal, regulatory or risk, and every MOVING ticker first.
3. Write a short brief, per ticker: what happened, the source and link, the
   move, and one line on why it matters to the setup (for example "earnings
   are this week: an overnight gap can jump past any stop").
4. If a story changes the picture, say so before `/trader-entry` and
   `/trader-exit`: an earnings date inside the trade, a halt, an offering.
   Never act on a headline alone.

During the session: `/loop 15m /trader-news`, or a scheduled task each
morning before the open.

## Example: the reel

Monday 2026-10-19, TSLA broke its opening range at 10:15 AM ET. The check at
10:15 (Yahoo Finance's TSLA feed, 16 headlines since 8:00) leads with the
morning's real stories: "Meta and Musk earnings and September pending home
sales: What to Watch" (8:00, earnings), "Tesla-SpaceX Merger Mania Strikes
Wall Street Ahead of Earnings" (8:04, earnings, deal), "Tech Stock Rebound
Nudges US Equity Futures Mostly Higher Pre-Bell" (8:02, macro). The brief:
"Tesla reports this week, so the stock can gap overnight; today's trade is
in and out before the close. No new 8-K." At 10:52 the price line reads
`TSLA 366.48 +3.31% vs yesterday's close 354.72 at 10:52 ET  MOVING`. When a
ticker has no news, say so rather than padding the brief.

## What it never does

- Never invents or embellishes a story, a quote or a number.
- Never trades on news, and never tells the user to buy or sell because of a
  headline.
- Never hammers a server: one request per feed per ticker, a pause between
  calls, and SEC's 10 requests a second limit stays far away.

## Safety

Education and tooling, not financial advice. This skill only reads and
reports. Nothing places an order except `/trader-broker`, after
`/trader-risk` passes and the user types an explicit yes for that order.
