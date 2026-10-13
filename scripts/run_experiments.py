"""Collect the controlled experiments requested by the Day 25B report."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gameday_lab.client import ResilientClient
from gameday_lab.factory import build_client
from gameday_lab.sim.config import LabConfig, load_config
from gameday_lab.sim.engine import run_scenario


class UnfilteredClient(ResilientClient):
    """Experiment-only client that deliberately ignores provider capabilities."""

    def ladder(self, task: str) -> list[str]:
        return list(self.order)


def run(cfg: LabConfig, scenario: str, seed: int = 25, *, unfiltered: bool = False) -> dict[str, Any]:
    client = (UnfilteredClient(cfg.provider_infos(), cfg.fallback_order, cfg.client, seed=seed)
              if unfiltered else build_client("resilient", cfg, seed=seed))
    metrics = run_scenario(cfg, scenario, client, seed).metrics()
    return {key: metrics.get(key) for key in (
        "availability", "faq_availability", "cache_hit_ratio", "stale_served", "wrong_answers",
        "wrong_answers_by_reason", "outdated_answers", "amplification", "retry_ratio",
        "recovery_s", "latency_p95_s", "give_up_reasons", "incompatible_routes",
        "retry_after_violations", "unneeded_failovers", "cost_per_good_turn",
    )}


def main() -> None:
    core = load_config("configs/gameday.yaml", "configs/scenarios.yaml")
    cache_cfg = load_config("configs/gameday.yaml", "configs/scenarios_cache.yaml")
    out: dict[str, Any] = {"seed": 25, "retry_budget": {}, "timeout_30s": {}, "tool_capability": {}, "cache": {}}

    for scenario in ("G2_overload_storm", "G3_brownout"):
        out["retry_budget"][scenario] = {}
        for enabled in (True, False):
            settings = {**core.client, "max_attempts_per_provider": 5,
                        "breaker": {**core.client["breaker"], "min_calls": 1_000_000_000}}
            if not enabled:
                settings.update({"retry_budget_ratio": 100, "retry_budget_max_tokens": 1.0e9,
                                 "retry_budget_min_per_s": 1.0e6})
            cfg = replace(core, client=settings)
            key = "budget_on" if enabled else "budget_off"
            out["retry_budget"][scenario][key] = run(cfg, scenario)

    for scenario in ("G6_provider_outage", "G4_slow_region"):
        out["timeout_30s"][scenario] = {
            "configured": run(core, scenario),
            "timeout_30s": run(replace(core, client={**core.client, "attempt_timeout_s": 30.0}), scenario),
        }

    out["tool_capability"]["G6_provider_outage"] = {
        "filtered": run(core, "G6_provider_outage"),
        "unfiltered": run(core, "G6_provider_outage", unfiltered=True),
    }

    for threshold in (0.80, float(cache_cfg.cache["similarity_threshold"]), 0.97):
        cfg = replace(cache_cfg, cache={**cache_cfg.cache, "similarity_threshold": threshold})
        out["cache"][f"threshold_{threshold:.2f}"] = run_cached(cfg)
    for ttl in (30.0, 60.0, 300.0):
        cfg = replace(cache_cfg, cache={**cache_cfg.cache, "ttl_s": ttl})
        out["cache"][f"ttl_{int(ttl)}"] = run_cached(cfg)
    cfg = replace(cache_cfg, cache={**cache_cfg.cache, "max_stale_s": 0.0})
    out["cache"]["stale_disabled"] = run_cached(cfg)

    target = Path("reports/experiments/results.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(target)


def run_cached(cfg: LabConfig) -> dict[str, Any]:
    client = build_client("cached", cfg, seed=25)
    metrics = run_scenario(cfg, "C1_faq_outage", client, 25).metrics()
    result = {key: metrics.get(key) for key in (
        "availability", "faq_availability", "cache_hit_ratio", "stale_served", "wrong_answers",
        "wrong_answers_by_reason", "outdated_answers", "cost_per_good_turn", "give_up_reasons",
    )}
    result["cache_entries_after"] = len(client.cache.entries)
    result["cache_entries_limit"] = client.cache.max_entries
    return result


if __name__ == "__main__":
    main()
