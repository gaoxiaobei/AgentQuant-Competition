"""Entrant-facing daily protocol. This module does not load market data."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

FactorValue = Annotated[float, Field(allow_inf_nan=False)] | None


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FactorRow(Contract):
    asset_id: str
    values: dict[str, FactorValue]


class Position(Contract):
    asset_id: str
    shares: int
    sellable_shares: int


class Snapshot(Contract):
    trading_date: date
    decision_at: datetime
    factors: tuple[FactorRow, ...]
    eligible_assets: tuple[str, ...]
    cash: Decimal
    positions: tuple[Position, ...]


class StrategyContext(Contract):
    seed: int


class Keep(Contract):
    action: Literal["KEEP"] = "KEEP"


class Weight(Contract):
    asset_id: str
    weight_bps: Annotated[int, Field(strict=True, ge=1, le=10_000)]


class Target(Contract):
    action: Literal["TARGET"] = "TARGET"
    weights: tuple[Weight, ...]


Decision = Annotated[Keep | Target, Field(discriminator="action")]


class Strategy(Protocol):
    def initialize(self, context: StrategyContext) -> None: ...

    def on_day(self, snapshot: Snapshot) -> Decision: ...
