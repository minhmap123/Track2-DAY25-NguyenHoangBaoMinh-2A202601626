"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        tier = pricing.recommend_tier(hpd, interruptible)
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od)
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "optimized_monthly": round(optimized_monthly), "savings_pct": round(savings_pct, 1)}


def run_v2(verbose: bool = True) -> dict:
    """Extension 1 -- recommend_tier_v2(): per-GPU spot risk + 1yr-vs-3yr reserved.

    Re-runs the same jobs through the improved policy and reports how the
    tier choice and monthly savings change vs. the baseline run() above.
    """
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        reserved_3yr_hr = num(c["reserved_3yr_hr"])
        # No 1yr price in the catalog -> derive it from the same on-demand
        # baseline the 3yr price uses, at the smaller 1yr discount.
        reserved_1yr_hr = od * (1 - 0.28)
        on_demand_cost = gpu_hours * od

        rec = pricing.recommend_tier_v2(hpd, interruptible, gpu_type=gtype)
        tier = rec["tier"]
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od,
                                                interrupt_rate=rec["interrupt_rate"])
            opt_cost = sim["spot_cost"]
        elif tier == "reserved_3yr":
            opt_cost = gpu_hours * reserved_3yr_hr
        elif tier == "reserved_1yr":
            opt_cost = gpu_hours * reserved_1yr_hr
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "interrupt_rate": rec["interrupt_rate"],
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    if verbose:
        print("\n== Extension 1: M3 with recommend_tier_v2() ==")
        print(f"{'job':18}{'gpu':7}{'tier':14}{'spot_risk':>10}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            risk = f"{r['interrupt_rate']:.1%}"
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:14}{risk:>10}"
                  f"${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly (v2): on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}"
              f"  ({savings_pct:.1f}% saved)")

    return {"recommendations": recs, "on_demand_monthly": round(on_demand_monthly),
            "optimized_monthly": round(optimized_monthly), "savings_pct": round(savings_pct, 1)}


if __name__ == "__main__":
    v1 = run()
    v2 = run_v2()
    print(f"\n== Comparison ==")
    print(f"v1 (flat 5% interrupt rate)      savings_pct = {v1['savings_pct']}%")
    print(f"v2 (per-GPU interrupt rate)      savings_pct = {v2['savings_pct']}%")
    for a, b in zip(v1["recommendations"], v2["recommendations"]):
        if a["optimized"] != b["optimized"]:
            print(f"  {a['job_id']:18} spot cost ${a['optimized']:,} -> ${b['optimized']:,} "
                  f"(real {a['gpu_type']} risk {b['interrupt_rate']:.1%} vs flat 5%)")
