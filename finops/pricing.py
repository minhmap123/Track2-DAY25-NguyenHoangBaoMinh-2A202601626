"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def recommend_tier(hours_per_day: float, interruptible: bool, reserved_discount: float = 0.45) -> str:
    """Pick a purchasing tier from a workload's duty cycle + interruptibility.

    DOCUMENTED simple policy (instructor extension point — swap in your own):
      - interruptible & not 24/7  -> 'spot'      (checkpoint and ride the discount)
      - duty cycle >= break-even  -> 'reserved'  (steady, high utilization)
      - otherwise                 -> 'on_demand' (spiky / low duty)
    """
    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        return "spot"
    if duty >= be:
        return "reserved"
    return "on_demand"


def cache_is_worth_it(
    avg_cache_reads: float,
    write_cost_per_m: float = 1.25,
    read_discount: float = 0.10,
) -> bool:
    """Extension 3: cache only pays for itself once reuse clears a break-even point.

    write_cost_per_m and read_discount are both expressed as a MULTIPLE of the
    normal (uncached) price/M-token -- e.g. a provider may charge ~1.25x to
    WRITE a cache entry and ~0.10x to READ one back. Each read saves
    (1 - read_discount) of normal price; the write cost is paid once. Caching
    is worth it once accumulated read savings clear that one-time write cost.
    """
    savings_per_read = 1.0 - read_discount
    if savings_per_read <= 0:
        return False
    return avg_cache_reads >= write_cost_per_m / savings_per_read


def cache_break_even_reads(write_cost_per_m: float = 1.25, read_discount: float = 0.10) -> float:
    """Minimum reuse count for a cached prefix to pay for its own write cost."""
    savings_per_read = 1.0 - read_discount
    if savings_per_read <= 0:
        return float("inf")
    return write_cost_per_m / savings_per_read


# Extension 1 -- illustrative per-GPU-type spot interruption rates. Scarce,
# high-demand SKUs (H100/H200/B200) get reclaimed more often than older,
# lower-demand ones (A10G/L4) once every tenant wants the same scarce card.
INTERRUPT_RATE_BY_GPU = {
    "H100": 0.07, "H200": 0.08, "B200": 0.09,
    "A100": 0.05, "MI300X": 0.06,
    "A10G": 0.02, "L4": 0.015,
}


def recommend_tier_v2(
    hours_per_day: float,
    interruptible: bool,
    gpu_type: str | None = None,
    reserved_discount_3yr: float = 0.45,
    reserved_discount_1yr: float = 0.28,
    interrupt_rate_by_gpu: dict | None = None,
) -> dict:
    """Extension 1: tier policy aware of per-GPU spot risk + 1yr-vs-3yr reserved.

    Differs from recommend_tier() in two ways:
    - Spot risk varies by GPU type instead of a single flat interrupt_rate.
    - A duty cycle that only clears the CHEAPER 1yr break-even (not the 3yr
      one) is recommended 1yr reserved -- lower discount, lower commitment
      risk -- rather than being force-fit into on_demand or a 3yr contract.
    """
    rates = interrupt_rate_by_gpu or INTERRUPT_RATE_BY_GPU
    interrupt_rate = rates.get(gpu_type, 0.05)
    duty = max(0.0, hours_per_day) / 24.0
    be_3yr = break_even_utilization(reserved_discount_3yr)
    be_1yr = break_even_utilization(reserved_discount_1yr)

    if interruptible and hours_per_day < 24:
        return {"tier": "spot", "interrupt_rate": interrupt_rate, "duty": round(duty, 3)}
    if duty >= be_3yr:
        return {"tier": "reserved_3yr", "interrupt_rate": interrupt_rate, "duty": round(duty, 3)}
    if duty >= be_1yr:
        return {"tier": "reserved_1yr", "interrupt_rate": interrupt_rate, "duty": round(duty, 3)}
    return {"tier": "on_demand", "interrupt_rate": interrupt_rate, "duty": round(duty, 3)}


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }
