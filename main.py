"""Momentum-confirmation paper-trading bot for the pump.fun replay (agent-fun/replay/v2).

Strategy, in one paragraph: the replay streams a hello, then one batch of market
events per slot; each batch may carry orders back. Fresh pump.fun launches are
mostly noise, so this bot never buys a launch on sight. A coin first has to prove
itself: enough trades, buy-side volume clearly dominating sell-side volume, and a
price already up at least 20% from its create price, all while it is still young.
Then the bot takes one fixed-size position (never a second one in the same coin),
and manages it with four exits: a take-profit, a trailing stop under the peak, a
hard stop, and a time stop. Every decision is a pure function of the batches seen
so far - no clock, no randomness - so the two graded executions agree byte for
byte.

Fees shape everything here: each side of a round trip pays roughly 1.25% in
protocol and creator fees plus a fixed tx fee, and a rejected order is not free
either, so slippage is left wide open (rejections for price movement are the
expensive failure mode) and every cap the hello announces (open positions, order
size as a share of the real reserve, orders per batch, free cash) is respected
before an order is sent, not after it bounces.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import makefun_bot  # noqa: E402

SOL = makefun_bot.LAMPORTS_PER_SOL

# --- entry rules -----------------------------------------------------------
STAKE_LAMPORTS = SOL // 20            # target buy size: 0.05 SOL
MIN_CAP_LAMPORTS = SOL // 33          # skip coins whose size cap is under ~0.03 SOL
MIN_RESERVE_LAMPORTS = 12 * SOL       # coin must hold at least 12 SOL of real reserve
MIN_TRADES = 25                       # proof of life before we consider a coin
MIN_BUY_SHARE = 0.70                  # buy volume must be >= 70% of total volume
MIN_GAIN_FROM_CREATE = 0.35           # price must be up >= 35% from the create price
MAX_GAIN_FROM_CREATE = 5.0            # ... but not already up 5x (exhausted top)
MAX_AGE_SLOTS = 3000                  # only enter young coins (~20 minutes of slots)
MIN_ROUND_TRIP_LAMPORTS = SOL // 100  # 0.01 SOL: the guardrail's minimum buy

# --- exit rules ------------------------------------------------------------
TAKE_PROFIT = 0.55                    # sell everything at +55%
TRAIL_ARM = 0.30                      # trailing stop arms at +30% ...
TRAIL_DROP = 0.78                     # ... and fires at 78% of the peak price
HARD_STOP = -0.30                     # sell everything at -30%
MAX_HOLD_SLOTS = 3000                 # time stop: ~20 minutes of slots

WIDE_SLIPPAGE_BPS = 10_000            # never reject for price movement

# --- bookkeeping -----------------------------------------------------------
# Per-coin tape aggregates, in first-seen order (dicts keep insertion order).
tape = {}          # mint -> {"buy": int, "sell": int, "create_price": float|None}
entered = {}       # mint -> True once we have ever sent a buy for it
positions_meta = {}  # mint -> {"entry_price": float, "peak_price": float, "entry_slot": int}
pending_side = {}  # mint -> "buy" | "sell" for orders sent but not yet filled


def spot_price(curve):
    """SOL per token at the curve's latest virtual reserves."""
    if curve is None or curve.virtual_token_reserves <= 0:
        return None
    return curve.virtual_quote_reserves / curve.virtual_token_reserves


def note_events(batch):
    """Fold this batch's events into the per-coin tape aggregates."""
    for e in batch["events"]:
        mint = e["mint"]
        rec = tape.get(mint)
        if rec is None:
            rec = tape[mint] = {"buy": 0, "sell": 0, "create_price": None}
        kind = e["event"]
        if kind == "CreateEvent":
            vt = int(e["virtual_token_reserves"])
            vq = int(e["virtual_quote_reserves"])
            if vt > 0:
                rec["create_price"] = vq / vt
        elif kind == "TradeEvent":
            amount = int(e["sol_amount"])
            if e["is_buy"]:
                rec["buy"] += amount
            else:
                rec["sell"] += amount


def note_fills(state, batch):
    """Learn entry prices from fills and clear pending flags."""
    for f in batch["fills"]:
        mint = f["mint"]
        pending_side.pop(mint, None)
        if f["status"] != "filled":
            continue
        if f["side"] == "buy":
            tokens = int(f["token_amount"])
            if tokens > 0:
                price = int(f["quote_lamports"]) / tokens
                positions_meta[mint] = {
                    "entry_price": price,
                    "peak_price": price,
                    "entry_slot": f["slot"],
                }
        elif f["side"] == "sell":
            positions_meta.pop(mint, None)


def sync_positions(state):
    """Drop metadata for positions the harness closed on its own."""
    for mint in list(positions_meta):
        if mint not in state.positions:
            del positions_meta[mint]


def exit_orders(state, batch):
    """One sell order per held position whose exit rule fired on this batch."""
    orders = []
    slot = batch["slot"]
    for mint, holding in state.positions.items():
        if pending_side.get(mint) == "sell":
            continue
        curve = state.curves.get(mint)
        if curve is None or curve.complete:
            continue  # the harness closes completed curves itself
        price = spot_price(curve)
        meta = positions_meta.get(mint)
        if price is None or meta is None:
            continue
        if price > meta["peak_price"]:
            meta["peak_price"] = price
        entry = meta["entry_price"]
        gain = price / entry - 1.0
        peak_gain = meta["peak_price"] / entry - 1.0
        fire = (
            gain >= TAKE_PROFIT
            or gain <= HARD_STOP
            or (peak_gain >= TRAIL_ARM and price <= meta["peak_price"] * TRAIL_DROP)
            or slot - meta["entry_slot"] >= MAX_HOLD_SLOTS
        )
        if fire:
            orders.append({
                "side": "sell",
                "mint": mint,
                "token_amount": holding.token_amount,
                "max_slippage_bps": WIDE_SLIPPAGE_BPS,
            })
            pending_side[mint] = "sell"
    return orders


def entry_orders(state, batch, budget):
    """Buys for coins that proved themselves on this batch and are still young."""
    orders = []
    caps = state.hello["caps"]
    tx = state.tx_fee_lamports()
    free = state.free_cash_lamports()
    open_slots = caps["max_open_positions"] - state.committed_position_count()
    slot = batch["slot"]
    for mint, curve in state.curves.items():
        if len(orders) >= budget or open_slots <= 0:
            break
        if mint in entered or mint in state.positions or pending_side.get(mint) == "buy":
            continue
        if curve.complete or curve.created_slot is None:
            continue
        if slot - curve.created_slot > MAX_AGE_SLOTS:
            continue
        if curve.trades < MIN_TRADES:
            continue
        if curve.real_quote_reserves < MIN_RESERVE_LAMPORTS:
            continue
        rec = tape.get(mint)
        if rec is None or rec["create_price"] is None:
            continue
        total = rec["buy"] + rec["sell"]
        if total <= 0 or rec["buy"] / total < MIN_BUY_SHARE:
            continue
        price = spot_price(curve)
        if price is None:
            continue
        gain = price / rec["create_price"] - 1.0
        if gain < MIN_GAIN_FROM_CREATE or gain > MAX_GAIN_FROM_CREATE:
            continue
        cap = state.max_buy_lamports(mint)
        amount = min(STAKE_LAMPORTS, cap)
        if amount < max(MIN_CAP_LAMPORTS, MIN_ROUND_TRIP_LAMPORTS):
            continue
        if free < amount + 2 * tx:
            continue
        orders.append({
            "side": "buy",
            "mint": mint,
            "quote_lamports": amount,
            "max_slippage_bps": WIDE_SLIPPAGE_BPS,
        })
        entered[mint] = True
        pending_side[mint] = "buy"
        free -= amount + tx
        open_slots -= 1
    return orders


def on_batch(state, batch):
    note_events(batch)
    note_fills(state, batch)
    sync_positions(state)
    sells = exit_orders(state, batch)
    room = state.hello["caps"]["max_orders_per_batch"] - len(sells)
    buys = entry_orders(state, batch, room) if room > 0 else []
    return sells + buys


if __name__ == "__main__":
    makefun_bot.run(on_batch)
