"""Golden set 在 NautilusTrader 适配层上的验证器 (G18-P6, 验收门禁 1)。

``docs/golden/`` 的 golden case 是市场规则的可执行事实。适配层
（``markets/nt/``）复用 ``markets/`` 的唯一事实源，本模块把每个 golden case
数据驱动地映射到适配层组件（FeeModel/FillModel/逐日盯市/换月/强平）或唯一
事实源接口，返回逐 case 的通过/失败明细，作为「删除旧实现」前的验收门禁。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from quant_platform.markets.cn_a import (
    AShareDailyState,
    ASharePosition,
    CashDividend,
    CorporateActionLedger,
    MembershipEvent,
    OrderSide,
    PositionLot,
    PriceLimitRule,
    SecurityStatus,
    SecurityStatusEvent,
    SplitAction,
    membership_as_of,
    security_status_as_of,
)
from quant_platform.markets.contracts import MarketId
from quant_platform.markets.cost import EquityCostModel, FuturesCostModel
from quant_platform.markets.futures import (
    CloseOffset,
    DeliveryPolicy,
    FeeRate,
    FeeSchedule,
    FuturesPosition,
    MarginSchedule,
    OpenInterestObservation,
    select_main_contract,
)
from quant_platform.markets.nt.futures_fee import close_offset_fee
from quant_platform.markets.nt.roll import build_roll_transitions
from quant_platform.markets.nt.settlement import SettlementLeg, settle_daily


@dataclass(frozen=True, slots=True)
class GoldenVerdict:
    case_id: str
    passed: bool
    detail: str


def _eq_decimal(actual: object, expected: object) -> bool:
    return Decimal(str(actual)) == Decimal(str(expected))


def verify_cn_a_case(case: dict[str, object]) -> GoldenVerdict:
    case_id = str(case["id"])
    kind = str(case["kind"])
    inputs = case["inputs"]
    expected = case["expected"]
    assert isinstance(inputs, dict)
    assert isinstance(expected, dict)
    try:
        if kind == "t_plus_one":
            position = ASharePosition(
                tuple(
                    PositionLot(
                        quantity=int(lot["quantity"]),
                        acquired_on=date.fromisoformat(str(lot["acquired_on"])),
                    )
                    for lot in inputs["lots"]
                )
            )
            sellable = position.sellable_quantity(
                date.fromisoformat(str(inputs["trade_date"]))
            )
            assert sellable == expected["sellable_quantity"]
        elif kind == "price_limit":
            lower, upper = PriceLimitRule(
                percentage=Decimal(str(inputs["percentage"])),
                tick_size=Decimal(str(inputs["tick_size"])),
            ).band(Decimal(str(inputs["basis_price"])))
            assert {"lower": str(lower), "upper": str(upper)} == expected
        elif kind == "tradability":
            assessment = AShareDailyState(
                halted=bool(inputs["halted"]),
                volume=int(inputs["volume"]),
                high=Decimal(str(inputs["high"])),
                low=Decimal(str(inputs["low"])),
                upper_limit=Decimal(str(inputs["upper_limit"])),
                lower_limit=Decimal(str(inputs["lower_limit"])),
            ).assess(OrderSide(str(inputs["side"])))
            assert {
                "certainty": assessment.certainty.value,
                "reason": assessment.reason,
            } == expected
        elif kind == "status":
            status_event = SecurityStatusEvent(
                status=SecurityStatus(str(inputs["status"])),
                announced_at=datetime.fromisoformat(str(inputs["announced_at"])),
                effective_from=date.fromisoformat(str(inputs["effective_from"])),
            )
            status = security_status_as_of(
                (status_event,),
                date.fromisoformat(str(inputs["trade_date"])),
                datetime.fromisoformat(str(inputs["decision_at"])),
            )
            assert status.value == expected["status"]
        elif kind == "membership":
            event = MembershipEvent(
                index_id=str(inputs["index_id"]),
                instrument_id=str(inputs["instrument_id"]),
                announced_at=datetime.fromisoformat(str(inputs["announced_at"])),
                effective_from=date.fromisoformat(str(inputs["effective_from"])),
                effective_to=None,
            )
            assert (
                membership_as_of(
                    (event,),
                    str(inputs["index_id"]),
                    str(inputs["instrument_id"]),
                    date.fromisoformat(str(inputs["trade_date"])),
                    datetime.fromisoformat(str(inputs["decision_at"])),
                )
                is expected["included"]
            )
        elif kind == "corporate_action":
            ledger = CorporateActionLedger(
                quantity=int(inputs["quantity"]),
                cash=Decimal(str(inputs["cash"])),
                cost_basis_per_share=Decimal(str(inputs["cost_basis_per_share"])),
            )
            if inputs["action"] == "cash_dividend":
                action: CashDividend | SplitAction = CashDividend(
                    record_date=date.fromisoformat(str(inputs["record_date"])),
                    ex_date=date.fromisoformat(str(inputs["ex_date"])),
                    payable_date=date.fromisoformat(str(inputs["payable_date"])),
                    cash_per_share=Decimal(str(inputs["cash_per_share"])),
                )
            else:
                action = SplitAction(
                    record_date=date.fromisoformat(str(inputs["record_date"])),
                    ex_date=date.fromisoformat(str(inputs["ex_date"])),
                    ratio=Decimal(str(inputs["ratio"])),
                )
            result = ledger.apply(action, date.fromisoformat(str(inputs["as_of"])))
            assert {
                "quantity": result.quantity,
                "cash": str(result.cash),
                "cost_basis_per_share": str(result.cost_basis_per_share),
            } == expected
        elif kind == "transaction_cost":
            model = EquityCostModel(
                model_id="cost://golden/v1",
                market=MarketId.CN_A,
                commission_rate=float(inputs["commission_rate"]),
                minimum_commission=float(inputs["minimum_commission"]),
                stamp_duty_rate=float(inputs["stamp_duty_rate"]),
                transfer_fee_rate=float(inputs["transfer_fee_rate"]),
                slippage_bps=0.0,
                impact_bps_per_adv=0.0,
                funding_rate_daily=0.0,
                borrow_rate_daily=0.0,
            )
            notional = Decimal(str(inputs["notional"]))
            buy_cost = model.single_side_cost(OrderSide.BUY, float(notional))
            assert _eq_decimal(buy_cost, expected["buy_cost"])
            if "sell_cost" in expected:
                sell_cost = model.single_side_cost(OrderSide.SELL, float(notional))
                assert _eq_decimal(sell_cost, expected["sell_cost"])
        else:
            raise AssertionError(f"unsupported golden case kind: {kind}")
        return GoldenVerdict(case_id=case_id, passed=True, detail="ok")
    except AssertionError as exc:
        return GoldenVerdict(case_id=case_id, passed=False, detail=str(exc))


def verify_futures_case(case: dict[str, object]) -> GoldenVerdict:
    case_id = str(case["id"])
    kind = str(case["kind"])
    inputs = case["inputs"]
    expected = case["expected"]
    assert isinstance(inputs, dict)
    assert isinstance(expected, dict)
    try:
        if kind == "settlement":
            result = settle_daily(
                (
                    SettlementLeg(
                        instrument_id="RB",
                        previous_quantity=int(inputs["previous_quantity"]),
                        previous_settlement=Decimal(str(inputs["previous_settlement"])),
                        opened_quantity=int(inputs["opened_quantity"]),
                        opened_price=Decimal(str(inputs["opened_price"])),
                        settlement_price=Decimal(str(inputs["settlement_price"])),
                    ),
                ),
                multiplier=Decimal(str(inputs["multiplier"])),
                fees=Decimal(str(inputs["fees"])),
            )
            assert _eq_decimal(result.mark_to_market, expected["mark_to_market"])
            assert result.ending_quantities["RB"] == expected["ending_quantity"]
        elif kind == "margin":
            schedule = MarginSchedule(
                exchange_rate=Decimal(str(inputs["exchange_rate"])),
                broker_rate=Decimal(str(inputs["broker_rate"])),
            )
            required = schedule.required_margin(
                Decimal(str(inputs["settlement_price"])),
                Decimal(str(inputs["multiplier"])),
                int(inputs["quantity"]),
            )
            assert _eq_decimal(required, expected["required_margin"])
        elif kind == "fee":
            fee_schedule = FeeSchedule(
                {
                    CloseOffset.CLOSE_TODAY: FeeRate(
                        per_lot=Decimal(str(inputs["close_today_per_lot"]))
                    ),
                    CloseOffset.CLOSE_YESTERDAY: FeeRate(
                        per_lot=Decimal(str(inputs["close_yesterday_per_lot"]))
                    ),
                }
            )
            fee = close_offset_fee(
                fee_schedule,
                CloseOffset(str(inputs["offset"])),
                int(inputs["quantity"]),
                Decimal(str(inputs["price"])),
                Decimal(str(inputs["multiplier"])),
            )
            assert _eq_decimal(fee, expected["fee"])
        elif kind == "close_offset":
            position = FuturesPosition(
                today_quantity=int(inputs["today_quantity"]),
                yesterday_quantity=int(inputs["yesterday_quantity"]),
            )
            closed = position.close(
                int(inputs["quantity"]), CloseOffset(str(inputs["offset"]))
            )
            assert {
                "today_quantity": closed.today_quantity,
                "yesterday_quantity": closed.yesterday_quantity,
            } == expected
        elif kind == "delivery_exit":
            policy = DeliveryPolicy(
                force_exit_date=date.fromisoformat(str(inputs["force_exit_date"])),
                delivery_allowed=False,
            )
            as_of = date.fromisoformat(str(inputs["as_of"]))
            assert policy.may_open(as_of) is expected["may_open"]
            assert policy.must_exit(as_of) is expected["must_exit"]
        elif kind == "main_contract":
            observations = tuple(
                OpenInterestObservation(
                    trade_date=date.fromisoformat(str(item["trade_date"])),
                    contract=str(item["contract"]),
                    delivery_month=int(item["delivery_month"]),
                    open_interest=Decimal(str(item["open_interest"])),
                )
                for item in inputs["observations"]
            )
            selected = select_main_contract(
                str(inputs["current_contract"]),
                date.fromisoformat(str(inputs["decision_date"])),
                observations,
                int(inputs["confirmation_days"]),
                Decimal(str(inputs["threshold"])),
            )
            assert selected == expected["contract"]
        elif kind == "night_trade_date":
            from zoneinfo import ZoneInfo

            from quant_platform.data_gateway.resolver import Bar, assign_trading_dates

            shanghai = ZoneInfo("Asia/Shanghai")
            timestamp = datetime.fromisoformat(str(inputs["timestamp"])).replace(
                tzinfo=shanghai
            )
            exchange_date = date.fromisoformat(str(inputs["exchange_trade_date"]))
            bar = Bar(
                timestamp=timestamp,
                open=1.0,
                high=1.0,
                low=1.0,
                close=1.0,
                volume=1.0,
            )
            assigned = assign_trading_dates((bar,), (exchange_date,))[0].trading_date
            assert assigned == date.fromisoformat(str(expected["trade_date"]))
        elif kind == "transaction_cost":
            model = FuturesCostModel(
                model_id="cost://golden/v1",
                market=MarketId.CN_COMMODITY_FUTURES,
                fee_rate=float(inputs["fee_rate"]),
                slippage_bps=0.0,
                impact_bps_per_adv=0.0,
                margin_rate=0.0,
                funding_rate_daily=0.0,
            )
            notional = (
                Decimal(str(inputs["price"]))
                * Decimal(str(inputs["multiplier"]))
                * Decimal(str(inputs["quantity"]))
            )
            single = model.single_side_cost(float(notional))
            round_trip = model.round_trip_cost(float(notional))
            assert _eq_decimal(single, expected["single_side_fee"])
            assert _eq_decimal(round_trip, expected["round_trip_fee"])
        else:
            raise AssertionError(f"unsupported golden case kind: {kind}")
        return GoldenVerdict(case_id=case_id, passed=True, detail="ok")
    except AssertionError as exc:
        return GoldenVerdict(case_id=case_id, passed=False, detail=str(exc))


def verify_golden_cases(
    market: str, cases: list[dict[str, object]]
) -> tuple[int, tuple[GoldenVerdict, ...]]:
    """验证一个市场的全部 golden case，返回 (通过数, 全部判定)。"""
    verify = verify_cn_a_case if market == "CN_A" else verify_futures_case
    verdicts = tuple(verify(case) for case in cases)
    passed = sum(1 for verdict in verdicts if verdict.passed)
    return passed, verdicts


def build_roll_from_main(
    current: str,
    decision_date: date,
    observations: tuple[OpenInterestObservation, ...],
    confirmation_days: int,
    threshold: Decimal,
    prices: dict[str, dict[date, Decimal]],
) -> object:
    """复用主力选择结果构造换月转换表（适配层 build_roll_transitions）。"""
    selected = select_main_contract(
        current, decision_date, observations, confirmation_days, threshold
    )
    if selected == current:
        return ()
    history = (
        (decision_date, current),
        (decision_date, selected),
    )
    return build_roll_transitions(history, prices)


__all__ = [
    "GoldenVerdict",
    "build_roll_from_main",
    "verify_cn_a_case",
    "verify_futures_case",
    "verify_golden_cases",
]
