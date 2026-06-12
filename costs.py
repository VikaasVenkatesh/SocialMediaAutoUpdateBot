"""
Tiny cost-estimation helper (the $0 PoC's spend guardrail).

Prices are USD per 1M tokens, approximate list prices for the models used here.
Update if Anthropic pricing changes — these only drive the printed estimate, not
billing. Estimates accumulate into the `runs` table.
"""

import db

# USD per 1,000,000 tokens (input, output).
PRICES = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
}
_DEFAULT = (1.00, 5.00)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICES.get(model, _DEFAULT)
    return (input_tokens / 1_000_000) * in_price + (
        output_tokens / 1_000_000
    ) * out_price


def log_spend(run_id: str, input_tokens: int, output_tokens: int, cost_usd: float):
    """Accumulate token + cost estimates onto the run ledger."""
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE runs SET "
            "  est_input_tokens  = COALESCE(est_input_tokens, 0)  + ?, "
            "  est_output_tokens = COALESCE(est_output_tokens, 0) + ?, "
            "  est_cost_usd      = COALESCE(est_cost_usd, 0)      + ? "
            "WHERE run_id = ?",
            (input_tokens, output_tokens, round(cost_usd, 6), run_id),
        )
