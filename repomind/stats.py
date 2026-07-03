from __future__ import annotations

import json
from pathlib import Path

from .config import workspace_data_dir
from .models import StatsResponse

# Rough, approximate $ per 1M tokens (input+output blended) used only to
# give the UI a ballpark "estimated savings" number. Not meant to match
# your actual bill -- real pricing varies by model, region, and changes
# over time. Treat this as a motivating estimate, not an invoice.
APPROX_COST_PER_1M_TOKENS_USD = 6.0
APPROX_TOKENS_PER_EXCHANGE = 1500  # rough question + context + answer size


def _stats_path(repo_root: Path) -> Path:
    return workspace_data_dir(repo_root) / "stats.json"


def load_stats(repo_root: Path) -> StatsResponse:
    path = _stats_path(repo_root)
    if path.exists():
        try:
            raw = json.loads(path.read_text())
            return StatsResponse.model_validate(raw)
        except Exception:
            pass
    return StatsResponse()


def _save(repo_root: Path, stats: StatsResponse) -> None:
    _stats_path(repo_root).write_text(stats.model_dump_json(indent=2))


def record_exchange(repo_root: Path, escalated: bool) -> StatsResponse:
    stats = load_stats(repo_root)
    if escalated:
        stats.escalated_count += 1
        stats.estimated_cloud_cost_usd += (APPROX_TOKENS_PER_EXCHANGE / 1_000_000) * APPROX_COST_PER_1M_TOKENS_USD
    else:
        stats.local_count += 1
        stats.estimated_savings_usd += (APPROX_TOKENS_PER_EXCHANGE / 1_000_000) * APPROX_COST_PER_1M_TOKENS_USD
    _save(repo_root, stats)
    return stats
