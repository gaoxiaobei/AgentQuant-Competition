"""Composition for the synthetic fixture and built-in strategies."""

import argparse
from functools import cache
from importlib.resources import files

from .contracts import EvaluationResult, RunSpec
from .demo_catalog import DATASET_ID, RULES_VERSION
from .evaluator import Dataset, Rules, evaluate
from .sdk import Decision, Keep, Snapshot, StrategyContext, Target, Weight

RULES = Rules(version=RULES_VERSION, initial_cash="100000.00", fee_bps=2, lot_size=100)


class CashStrategy:
    def initialize(self, context: StrategyContext) -> None:
        pass

    def on_day(self, snapshot: Snapshot) -> Decision:
        return Keep()


class FactorRankStrategy(CashStrategy):
    def on_day(self, snapshot: Snapshot) -> Decision:
        ranked = {
            row.asset_id: row.values["f001"]
            for row in snapshot.factors
            if row.asset_id in snapshot.eligible_assets and row.values.get("f001") is not None
        }
        if not ranked:
            return Keep()
        asset_id = max(ranked, key=ranked.__getitem__)
        return Target(weights=(Weight(asset_id=asset_id, weight_bps=5000),))


BASELINES = {"cash": CashStrategy, "factor-rank": FactorRankStrategy}


@cache
def load_dataset(dataset_id: str) -> Dataset:
    if dataset_id != DATASET_ID:
        raise ValueError("unknown demo dataset")
    return Dataset.model_validate_json(files("agentquant").joinpath("synthetic-v1.json").read_bytes())


def run(spec: RunSpec) -> EvaluationResult:
    if spec.rules_version != RULES.version:
        raise ValueError("unknown demo rules version")
    return evaluate(load_dataset(spec.dataset_id), BASELINES[spec.baseline_id](), RULES, spec.seed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bundled AgentQuant baseline.")
    parser.add_argument("--baseline", choices=tuple(BASELINES), default="factor-rank")
    args = parser.parse_args()
    print(evaluate(load_dataset(DATASET_ID), BASELINES[args.baseline](), RULES).model_dump_json(indent=2))


if __name__ == "__main__":
    main()
