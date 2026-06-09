# Paper trading

A live paper-trading tracker. **No real money, no orders** — it logs hypothetical
positions and marks them to *live* Polymarket prices. Built so I (the assistant) log a
trade when you describe it in chat; you read the book here.

## What it tracks
- **Positions** — every trade you've opened (`positions.json`): venue, market, outcome,
  side, fill price, dollars in, shares.
- **Money in** — total staked across the book.
- **Unrealized P&L** — open positions marked to the current live price.
- **Realized P&L** — closed positions, net of a modeled round-trip cost.

## Commands
```
python paper/paper.py open --market <slug> --outcome "<leg>" --side yes --price 0.11 --stake 100 --note "..."
python paper/paper.py mark        # live unrealized P&L of open positions
python paper/paper.py close <id>  # close at the live price (or --price 0.18)
python paper/paper.py report      # full book: money in, unrealized, realized, combined
```

## How a trade flows
1. You say it in chat, e.g. *"fade Brazil champion in the elimination market, $100 at 0.11."*
2. I resolve the market slug + leg and run `open`.
3. Any time, `mark`/`report` fetches live prices and shows P&L.
4. You (or I, on your call) `close` a position; realized P&L lands in the monthly total.

## Honest notes
- Prices are the *current real* market price each time you run it. **It can't predict the
  future price** — `mark` shows what a position is worth *now*; exit value is known only
  when you close.
- P&L: `shares = stake / fill`, `value = shares × price`, `pnl = value − stake`. Realized
  P&L subtracts a modeled `COST_BPS` (default 100 bps) round-trip cost.
- Paper only — this is F-1-safe and doubles as a timestamped record of your trade ideas.
