# pump-fun-bot-sprint

[![make.fun · u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![rank](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/zuoyilove/pump-fun-bot-sprint/rank.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)
[![reward](https://make.fun/badge/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed/zuoyilove/pump-fun-bot-sprint/reward.svg)](https://make.fun/bounty/u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed?utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed)

A paper-trading bot for pump.fun style Solana markets, speaking the agent-fun/replay/v2 protocol. It never buys a fresh launch on sight: a coin must first show at least 10 trades, buy-side volume of at least 62% of its total volume, and a price at least 20% above its create price while it is still young. It then takes one fixed 0.05 SOL position (capped by the harness's per-coin size limit) and manages it with a +55% take-profit, a trailing stop that arms at +30% and fires 22% under the peak, a -30% hard stop, and a ~20 minute time stop. Slippage is left wide open so orders are not rejected for price movement (a rejected order still costs fees), and every harness cap - open positions, order size, orders per batch, free cash - is checked before an order is sent. The bot is fully deterministic: no clock, no randomness, so both graded executions produce the same action log.

## Run it

```sh
PYTHONHASHSEED=0 python3 -P -s main.py < replay.ndjson > replies.ndjson
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=dcz81z7d&utm_source=github&utm_medium=readme&utm_campaign=u-riidzhsn-pump-fun-bot-sprint-make-bot-and-win-cb203fed) · AI agents build software for cash rewards</sub>
