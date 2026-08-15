"""期货换月转换表 (G18-P3)。

NautilusTrader 的连续合约拼接只接受显式转换表
（``continuous_future_transitions``：转换时间、前后合约、前后价格），
引擎不发现换月点、不选合约、不推断价差。本模块把 ``markets/futures.py``
的持仓量确认式主力选择输出（唯一事实源）转成转换表，供 DataEngine 拼接。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RollTransition:
    transition_date: date
    from_contract: str
    to_contract: str
    from_price: Decimal
    to_price: Decimal

    def __post_init__(self) -> None:
        for contract in (self.from_contract, self.to_contract):
            if not contract or contract.strip() != contract:
                raise ValueError("contracts must be non-empty")
        if self.from_contract == self.to_contract:
            raise ValueError("from and to contracts must differ")
        if self.from_price <= 0 or self.to_price <= 0:
            raise ValueError("transition prices must be positive")

    def payload(self) -> dict[str, object]:
        return {
            "transition_date": self.transition_date.isoformat(),
            "from_contract": self.from_contract,
            "to_contract": self.to_contract,
            "from_price": str(self.from_price),
            "to_price": str(self.to_price),
        }


def build_roll_transitions(
    main_contract_by_date: tuple[tuple[date, str], ...],
    contract_prices: dict[str, dict[date, Decimal]],
) -> tuple[RollTransition, ...]:
    """把主力合约历史转成换月转换表。

    ``main_contract_by_date`` 按日期升序给出每日主力合约；连续两天主力
    合约不同即发生换月，用双方在换月日的价格构成一条转换记录。
    """
    if not main_contract_by_date:
        return ()
    transitions: list[RollTransition] = []
    for index in range(1, len(main_contract_by_date)):
        prev_date, prev_contract = main_contract_by_date[index - 1]
        curr_date, curr_contract = main_contract_by_date[index]
        if prev_contract == curr_contract:
            continue
        from_price = contract_prices.get(prev_contract, {}).get(curr_date)
        to_price = contract_prices.get(curr_contract, {}).get(curr_date)
        if from_price is None or to_price is None:
            continue
        transitions.append(
            RollTransition(
                transition_date=curr_date,
                from_contract=prev_contract,
                to_contract=curr_contract,
                from_price=from_price,
                to_price=to_price,
            )
        )
    return tuple(transitions)
