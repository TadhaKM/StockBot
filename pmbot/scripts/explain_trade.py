"""
Explain one full trade end-to-end.

Builds a hand-crafted market that satisfies every gate, runs it through
the real pipeline (filter -> research -> predict -> risk -> orderbook -> execute),
and prints a plain-English reason at every stage so you can trace WHY the
trade was placed.

We inject a deterministic predictor (no LLM / no news) so the outcome is
reproducible. Every other module is real.

Run:  python scripts/explain_trade.py
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.rules import load_rules
from src.execution.orderbook import OrderBook
from src.execution.paper import PaperExecutor
from src.filter.market_filter import MarketFilter, ranking_score
from src.prediction.base import BasePredictor, PredictionResult
from src.prediction.engine import PredictionEngine
from src.research.researcher import ResearchResult
from src.risk.manager import RiskManager
from src.scanner.base import Market

_W = 74


def _h(title: str) -> None:
    print(f"\n{'=' * _W}\n  {title}\n{'=' * _W}")


def _bullet(label: str, value: str, ok: bool = True) -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label:<30} {value}")


def _line(msg: str) -> None:
    print(f"  {msg}")


# ── Deterministic predictor ─────────────────────────────────────────────────

class _DemoPredictor(BasePredictor):
    """Returns a hand-crafted strong signal so we can watch execution happen."""
    name = "demo-strong-yes"

    async def predict(self, market: Market, research: ResearchResult) -> PredictionResult:
        # p_model beats p_market by 14 cents, well above the 5-cent min_edge.
        # confidence at 0.72 clears the 0.6 gate.
        return PredictionResult(
            market_id=market.id,
            p_model=0.75,
            p_market=market.mid_price,
            confidence=0.72,
            model_name=self.name,
            rationale="Hand-crafted demo signal: strong edge, high confidence.",
        )


# ── Hand-crafted market ──────────────────────────────────────────────────────

def _demo_market() -> Market:
    """One market that passes every filter by construction."""
    return Market(
        id="demo-001",
        title="Will Team A win the championship final?",
        platform="polymarket",
        category="sports",
        bid=0.60,
        ask=0.62,            # spread = 2c, under the 3c cap
        volume_usd=75_000,   # well above the 500 min
        orderbook_depth=8_000,  # well above the 100 min
        close_time=datetime.now(timezone.utc) + timedelta(days=5),
    )


# ── Main narrative ──────────────────────────────────────────────────────────

async def main() -> None:
    rules = load_rules()
    market = _demo_market()
    tmp = Path(tempfile.mkdtemp(prefix="explain_trade_"))

    _h("DEMO MARKET")
    _line(f"id:       {market.id}")
    _line(f"title:    {market.title}")
    _line(f"book:     bid={market.bid}  ask={market.ask}  "
          f"spread={market.spread:.2f}  mid={market.mid_price:.2f}")
    _line(f"volume:   ${market.volume_usd:,.0f}  depth=${market.orderbook_depth:,.0f}")
    _line(f"expiry:   {market.days_to_close:.1f} days")

    # ── 1. FILTER ──────────────────────────────────────────────────────────
    _h("STAGE 1 - FILTER  (quality gates from trading_rules.yaml)")
    mr = rules.market
    _bullet("spread <= max_spread",
            f"{market.spread:.2f} <= {mr.max_spread}",
            market.spread <= mr.max_spread)
    _bullet("volume >= min_volume",
            f"${market.volume_usd:,.0f} >= ${mr.min_volume:,.0f}",
            market.volume_usd >= mr.min_volume)
    _bullet("depth >= min_orderbook_depth",
            f"${market.orderbook_depth:,.0f} >= ${mr.min_orderbook_depth:,.0f}",
            market.orderbook_depth >= mr.min_orderbook_depth)
    _bullet("days_to_close <= max_days",
            f"{market.days_to_close:.1f} <= {mr.max_days_to_expiry}",
            market.days_to_close <= mr.max_days_to_expiry)

    scored = MarketFilter(rules=rules).run([market])
    if not scored:
        _line("  >> filter rejected; stopping demo.")
        return
    score = ranking_score(market, rules)
    _line(f"  ranking score: {score:.1f}/100  (volume*35% + tightness*30% + depth*20% + urgency*15%)")

    # ── 2. RESEARCH ────────────────────────────────────────────────────────
    _h("STAGE 2 - RESEARCH")
    research = ResearchResult(market_id=market.id, articles=[], summary="(demo: no news fetched)")
    _line("0 articles fetched (no news API key in demo). Real predictors would")
    _line("use this to adjust their prior; for the demo we override that with")
    _line("a hand-crafted strong signal so execution actually happens.")

    # ── 3. PREDICT ─────────────────────────────────────────────────────────
    _h("STAGE 3 - PREDICT")
    engine = PredictionEngine(predictor=_DemoPredictor(), rules=rules)
    signal = await engine.run(market, research)
    pred = signal.prediction
    _line(f"p_market (mid):   {pred.p_market:.4f}")
    _line(f"p_model (demo):   {pred.p_model:.4f}")
    _line(f"edge:             {pred.edge:+.4f}  -> side = {pred.recommended_side.upper()}")
    _line(f"confidence:       {pred.confidence:.2f}")
    _bullet("edge >= min_edge",
            f"{abs(pred.edge):.4f} >= {rules.edge.min_edge}",
            abs(pred.edge) >= rules.edge.min_edge)
    _bullet("confidence >= min_confidence",
            f"{pred.confidence:.2f} >= {rules.edge.min_confidence}",
            pred.confidence >= rules.edge.min_confidence)
    _bullet("produced a signal", "yes" if signal.is_signal else "NO", signal.is_signal)
    if not signal.is_signal:
        _line("  >> no signal; stopping demo.")
        return

    # ── 4. RISK ────────────────────────────────────────────────────────────
    _h("STAGE 4 - RISK  (bankroll protection)")
    risk = RiskManager(open_market_ids=set())
    decision = risk.evaluate(pred)
    _bullet("edge above threshold",
            f"|{pred.edge:+.4f}| > min",
            True)
    _bullet("not already holding", "no open position in this market", True)
    from src.config import cfg
    _bullet("position slot available",
            f"0 / {cfg.risk.max_open_positions} open", True)
    _bullet("Kelly sized",
            f"${decision.size_usd:.2f}  (fractional Kelly, capped by max_bankroll_fraction)",
            decision.approved)
    _bullet("approved", decision.reason, decision.approved)
    if not decision.approved:
        _line("  >> risk rejected; stopping demo.")
        return

    # ── 5. ORDERBOOK ───────────────────────────────────────────────────────
    _h("STAGE 5 - ORDERBOOK  (slippage + depth safety)")
    book = OrderBook.from_market(market)
    check = book.is_trade_safe(pred.recommended_side, decision.size_usd, rules)
    fill = book.estimate_fill_price(pred.recommended_side, decision.size_usd)
    _line(f"synthetic book:   best_bid={book.best_bid:.4f}  best_ask={book.best_ask:.4f}")
    _line(f"fill simulation:  vwap={fill.fill_price:.4f}  "
          f"slippage={fill.slippage:.4f}  levels={fill.levels_consumed}  "
          f"fully_filled={fill.fully_filled}")
    _bullet("slippage within max",
            f"{fill.slippage:.4f} <= {rules.execution.max_slippage}",
            fill.slippage <= rules.execution.max_slippage)
    _bullet("depth sufficient", "yes" if fill.fully_filled else "no", fill.fully_filled)
    _bullet("all orderbook checks", "passed" if check else f"failed: {check.failures}", bool(check))
    if not check:
        _line("  >> orderbook rejected; stopping demo.")
        return

    # ── 6. EXECUTE ─────────────────────────────────────────────────────────
    _h("STAGE 6 - EXECUTE  (paper trading engine)")
    executor = PaperExecutor(
        positions_file=tmp / "open_positions.json",
        trades_log=tmp / "trade_log.jsonl",
        closed_log=tmp / "closed_positions.jsonl",
        stop_file=tmp / "STOP",
    )
    limit_price = pred.p_model if pred.edge > 0 else 1 - pred.p_model
    _line(f"limit_price:      {limit_price:.4f}  (side-native, = model fair value)")
    _line(f"size requested:   ${decision.size_usd:.2f}")
    rec = await executor.submit(
        market_id=market.id,
        platform=market.platform,
        side=pred.recommended_side,
        size_usd=decision.size_usd,
        limit_price=limit_price,
        book=book,
    )
    if rec is None:
        _line("  >> paper engine rejected; stopping demo.")
        return
    _line(f"FILLED: entry={rec.fill_price:.4f}  contracts={rec.contracts:.2f}  "
          f"size=${rec.size_usd:.2f}")
    _line(f"  trade_id: {rec.trade_id}")

    # ── 7. ONE-LINE STORY ──────────────────────────────────────────────────
    _h("ONE-LINE EXPLANATION")
    _line(f"Bought {rec.contracts:.2f} {rec.side.upper()} contracts in '{market.title}'")
    _line(f"for ${rec.size_usd:.2f} at {rec.fill_price:.4f} each because:")
    _line(f"  - filter:    tight spread ({market.spread:.2f}), deep book "
          f"(${market.orderbook_depth:,.0f}), "
          f"strong volume (${market.volume_usd:,.0f})")
    _line(f"  - predict:   model saw p={pred.p_model:.2f} vs market "
          f"p={pred.p_market:.2f} -> {pred.edge:+.2f} edge, conf {pred.confidence:.2f}")
    _line(f"  - risk:      Kelly sized ${decision.size_usd:.2f} ({decision.reason})")
    _line(f"  - orderbook: fill vwap {fill.fill_price:.4f}, "
          f"slippage {fill.slippage:.4f} within limits")
    _line(f"  - execute:   book accepted the limit, paper engine filled it.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
