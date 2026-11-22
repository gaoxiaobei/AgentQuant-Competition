"""Daily evaluation over a supplied dataset and a trusted strategy adapter."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter, model_validator

from .contracts import EquityPoint, EvaluationResult, Metrics, Trade
from .sdk import Contract, Decision, FactorValue, Position, Snapshot, Strategy, StrategyContext, Target

CENT = Decimal("0.01")
BASIS_POINTS = 10_000
decision_adapter = TypeAdapter(Decision)


class MarketRow(Contract):
    asset_id: str
    open: Annotated[Decimal, Field(gt=0)]
    close: Annotated[Decimal, Field(gt=0)]
    buyable: bool = True
    sellable: bool = True


class TimedFactors(Contract):
    asset_id: str
    available_at: AwareDatetime
    values: dict[str, FactorValue]


class MarketDay(Contract):
    trading_date: date
    decision_at: AwareDatetime
    market: tuple[MarketRow, ...]
    factors: tuple[TimedFactors, ...]


class Dataset(Contract):
    schema_version: Literal["1"]
    id: str
    days: Annotated[tuple[MarketDay, ...], Field(min_length=2)]

    @model_validator(mode="after")
    def check_rows(self) -> "Dataset":
        dates = [day.trading_date for day in self.days]
        if dates != sorted(set(dates)):
            raise ValueError("trading dates must be unique and in order")
        # The synthetic feed supplies a mark for every instrument on every date.
        assets = {row.asset_id for row in self.days[0].market}
        for day in self.days:
            market = [row.asset_id for row in day.market]
            factors = [row.asset_id for row in day.factors]
            if set(market) != assets or len(market) != len(assets):
                raise ValueError("each day must supply one market row per asset")
            if len(factors) != len(set(factors)) or not set(factors) <= assets:
                raise ValueError("factor rows must have unique, known assets")
        return self


class Rules(Contract):
    version: str
    initial_cash: Annotated[Decimal, Field(gt=0, decimal_places=2)]
    fee_bps: Annotated[int, Field(ge=0, lt=BASIS_POINTS)]
    lot_size: Annotated[int, Field(gt=0)]


def evaluate(dataset: Dataset, strategy: Strategy, rules: Rules, seed: int = 0) -> EvaluationResult:
    cash = rules.initial_cash
    holdings: dict[str, int] = {}
    orders: dict[str, int] = {}
    equity: list[EquityPoint] = []
    trades: list[Trade] = []
    strategy.initialize(StrategyContext(seed=seed))

    for index, day in enumerate(dataset.days):
        market = {row.asset_id: row for row in day.market}
        bought_today: dict[str, int] = {}
        for asset_id, quantity in sorted(orders.items(), key=lambda item: (item[1] > 0, item[0])):
            row = market[asset_id]
            if quantity < 0 and row.sellable:
                shares = min(-quantity, holdings[asset_id])
                side = "SELL"
            elif quantity > 0 and row.buyable:
                shares = affordable_shares(quantity, row.open, cash, rules)
                side = "BUY"
            else:
                continue
            if shares == 0:
                continue
            amount = money(row.open * shares)
            fee = money(amount * rules.fee_bps / BASIS_POINTS)
            cash += (amount if side == "SELL" else -amount) - fee
            current = holdings.get(asset_id, 0) + (shares if side == "BUY" else -shares)
            if current:
                holdings[asset_id] = current
            else:
                holdings.pop(asset_id, None)
            if side == "BUY":
                bought_today[asset_id] = shares
            trades.append(Trade(
                trading_date=day.trading_date, asset_id=asset_id, side=side,
                shares=shares, price=row.open, fee=fee,
            ))

        nav = money(cash + sum(market[asset_id].close * shares for asset_id, shares in holdings.items()))
        equity.append(EquityPoint(trading_date=day.trading_date, equity=nav))
        if index == len(dataset.days) - 1:
            break

        snapshot = Snapshot(
            trading_date=day.trading_date,
            decision_at=day.decision_at,
            factors=tuple(
                {"asset_id": row.asset_id, "values": row.values}
                for row in sorted(day.factors, key=lambda row: row.asset_id)
                if row.available_at <= day.decision_at
            ),
            eligible_assets=tuple(sorted(row.asset_id for row in day.market if row.buyable)),
            cash=cash,
            positions=tuple(
                Position(
                    asset_id=asset_id,
                    shares=shares,
                    sellable_shares=shares - bought_today.get(asset_id, 0),
                )
                for asset_id, shares in sorted(holdings.items())
            ),
        )
        decision = decision_adapter.validate_python(strategy.on_day(snapshot))
        orders = target_orders(decision, holdings, market, nav, rules.lot_size)

    high = rules.initial_cash
    drawdown = Decimal(0)
    for point in equity:
        high = max(high, point.equity)
        drawdown = max(drawdown, (high - point.equity) / high)
    return EvaluationResult(
        metrics=Metrics(
            initial_cash=rules.initial_cash,
            final_equity=equity[-1].equity,
            net_return=equity[-1].equity / rules.initial_cash - 1,
            max_drawdown=drawdown,
            total_fees=money(sum((trade.fee for trade in trades), Decimal(0))),
        ),
        equity=tuple(equity),
        trades=tuple(trades),
    )


def target_orders(
    decision: Decision, holdings: dict[str, int], market: dict[str, MarketRow], nav: Decimal, lot_size: int
) -> dict[str, int]:
    if not isinstance(decision, Target):
        return {}
    weights = {weight.asset_id: weight.weight_bps for weight in decision.weights}
    if len(weights) != len(decision.weights) or sum(weights.values()) > BASIS_POINTS:
        raise ValueError("duplicate assets or total weight above 10,000 bps")
    if any(asset not in market or not market[asset].buyable for asset in weights):
        raise ValueError("target assets must be in the eligible universe")
    targets = {
        asset: int(nav * weight / BASIS_POINTS // (market[asset].close * lot_size)) * lot_size
        for asset, weight in weights.items()
    }
    return {
        asset: targets.get(asset, 0) - holdings.get(asset, 0)
        for asset in targets.keys() | holdings.keys()
        if targets.get(asset, 0) != holdings.get(asset, 0)
    }


def affordable_shares(quantity: int, price: Decimal, cash: Decimal, rules: Rules) -> int:
    low, high = 0, quantity // rules.lot_size
    while low < high:
        mid = (low + high + 1) // 2
        amount = money(price * mid * rules.lot_size)
        if amount + money(amount * rules.fee_bps / BASIS_POINTS) <= cash:
            low = mid
        else:
            high = mid - 1
    return low * rules.lot_size


def money(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)
