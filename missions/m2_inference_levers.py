"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        opt_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
    }


def run_cache_extension(verbose: bool = True) -> dict:
    """Extension 3 -- gate prompt-cache savings behind cache_is_worth_it().

    Data has no explicit "times this prefix was reused" column, so we proxy
    avg_cache_reads with the number of requests sharing a (team, project) --
    those requests plausibly reuse the same cached system/context prefix.
    Reports the break-even reuse count vs. the actual reuse in this traffic,
    and what the optimized cost WOULD be if a project fell below break-even.
    """
    rows = load_csv("token_usage.csv")
    group_sizes: dict[tuple[str, str], int] = {}
    for r in rows:
        key = (r["team"], r["project"])
        group_sizes[key] = group_sizes.get(key, 0) + 1

    break_even = pricing.cache_break_even_reads()
    verdicts = {k: pricing.cache_is_worth_it(v) for k, v in group_sizes.items()}

    gated_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        key = (r["team"], r["project"])
        cached_in = cached if verdicts[key] else 0  # drop cache credit if not worth it
        pin, pout = MODEL_PRICES[r["route_tier"]]
        gated_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached_in, batch=is_batch)

    gated_pm = pricing.dollars_per_million(gated_cost, total_tokens)

    if verbose:
        print("\n== Extension 3: cache_is_worth_it() gate ==")
        print(f"break-even reuse count: {break_even:.2f} reads (write_cost=1.25x, read_discount=0.10x)")
        print(f"{'team/project':28}{'reads':>8}{'worth it?':>12}")
        for (team, project), n in sorted(group_sizes.items(), key=lambda kv: kv[1]):
            print(f"{team + '/' + project:28}{n:>8}{'YES' if verdicts[(team, project)] else 'NO':>12}")
        all_worth_it = all(verdicts.values())
        note = "every group clears break-even -> no change" if all_worth_it else "some groups gated off"
        print(f"\nGate-applied $/1M-token: ${gated_pm:.3f}  ({note})")

    return {"break_even_reads": round(break_even, 2), "gated_per_m": round(gated_pm, 3),
            "verdicts": {f"{k[0]}/{k[1]}": v for k, v in verdicts.items()}}


if __name__ == "__main__":
    run()
    run_cache_extension()
