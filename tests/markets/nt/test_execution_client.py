from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from nautilus_trader.model.orders import LimitOrder, MarketOrder

from quant_platform.execution.contracts import OrderInstruction
from quant_platform.execution.safety import KillSwitch, KillSwitchState, SafetyLimits
from quant_platform.markets.cn_a import OrderSide
from quant_platform.markets.nt.execution_client import NautilusOrderGateway
from quant_platform.markets.nt.instruments import equity_instrument


def armed_switch() -> KillSwitch:
    return KillSwitch(
        switch_id="execution-cn-a",
        state=KillSwitchState.ARMED,
        tripped_by=None,
        tripped_at=None,
        reason=None,
    )


def tripped_switch() -> KillSwitch:
    return armed_switch().trip("risk-officer-1", "data anomaly", datetime.now(UTC))


def limits(**kwargs: object) -> SafetyLimits:
    defaults: dict[str, object] = {
        "notional_cap": Decimal("100000"),
        "max_order_quantity": None,
    }
    defaults.update(kwargs)
    return SafetyLimits(**defaults)  # type: ignore[arg-type]


def instruction(quantity: int = 100) -> OrderInstruction:
    return OrderInstruction(
        order_id="order-1",
        instrument_id="600000.SH",
        side=OrderSide.BUY,
        quantity=quantity,
        idempotency_key="idem-1",
    )


def test_kill_switch_blocks_submission() -> None:
    gateway = NautilusOrderGateway(limits=limits(), kill_switch=tripped_switch())
    instrument = equity_instrument(symbol="600000")

    result = gateway.submit(instruction(), instrument, price=Decimal("10"))

    assert not result.accepted
    assert result.reason == "kill_switch"


def test_notional_cap_blocks_submission() -> None:
    gateway = NautilusOrderGateway(
        limits=limits(notional_cap=Decimal("100")), kill_switch=armed_switch()
    )
    instrument = equity_instrument(symbol="600000")

    result = gateway.submit(instruction(quantity=100), instrument, price=Decimal("10"))

    assert not result.accepted
    assert result.reason == "notional_cap_exceeded"


def test_market_order_accepted() -> None:
    gateway = NautilusOrderGateway(limits=limits(), kill_switch=armed_switch())
    instrument = equity_instrument(symbol="600000")

    result = gateway.submit(instruction(), instrument, price=Decimal("10"))

    assert result.accepted
    assert result.order is not None
    assert isinstance(result.order, MarketOrder)


def test_limit_order_accepted() -> None:
    gateway = NautilusOrderGateway(limits=limits(), kill_switch=armed_switch())
    instrument = equity_instrument(symbol="600000")

    result = gateway.submit(
        instruction(), instrument, price=Decimal("10"), limit_price=Decimal("9.8")
    )

    assert result.accepted
    assert result.order is not None
    assert isinstance(result.order, LimitOrder)


def test_max_order_quantity_blocks_submission() -> None:
    gateway = NautilusOrderGateway(
        limits=limits(max_order_quantity=50), kill_switch=armed_switch()
    )
    instrument = equity_instrument(symbol="600000")

    result = gateway.submit(instruction(quantity=100), instrument, price=Decimal("10"))

    assert not result.accepted
    assert result.reason == "order_quantity_exceeded"
