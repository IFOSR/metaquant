"""Paper account lifecycle service.

Creation binds a FROZEN strategy draft to an immutable content-addressed
artifact and an account row. The artifact is re-verified from storage before
any future runtime work consumes it, so a mutated draft can never trade.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from quant_platform.paper.artifact import (
    FrozenStrategyArtifact,
    StrategyArtifactStore,
)
from quant_platform.paper.contracts import (
    FREQUENCIES,
    PaperAccount,
    PaperAccountError,
    PaperAccountState,
    next_state,
)
from quant_platform.paper.repository import SqlAlchemyPaperRepository
from quant_platform.strategy_generation.repository import SqlAlchemyStrategyRepository
from quant_platform.strategy_generation.security import scan_strategy_source

_DEFAULT_INITIAL_CASH = Decimal("1000000")


class PaperAccountService:
    def __init__(
        self,
        *,
        repository: SqlAlchemyPaperRepository,
        artifacts: StrategyArtifactStore,
        drafts: SqlAlchemyStrategyRepository,
    ) -> None:
        self._repository = repository
        self._artifacts = artifacts
        self._drafts = drafts

    def create_account(
        self,
        *,
        actor_id: str,
        draft_id: str,
        initial_cash: Decimal | None = None,
    ) -> PaperAccount:
        draft = self._drafts.get_draft(draft_id)
        if draft is None:
            raise PaperAccountError(f"strategy draft not found: {draft_id}")
        if draft.state != "FROZEN" or draft.code is None or draft.content_hash is None:
            raise PaperAccountError(
                "only FROZEN strategy drafts can open paper accounts"
            )
        if draft.frequency not in FREQUENCIES:
            raise PaperAccountError(
                "paper simulation currently supports frequencies "
                f"{', '.join(FREQUENCIES)}; this strategy uses {draft.frequency}"
            )
        violations = scan_strategy_source(draft.code)
        if violations:
            raise PaperAccountError(
                "strategy code rejected by security policy: " + "; ".join(violations)
            )
        artifact = FrozenStrategyArtifact(
            draft_id=draft.id,
            market=draft.market,
            instrument_ids=tuple(draft.instrument_ids),
            frequency=draft.frequency,
            code=draft.code,
        )
        address = self._artifacts.freeze(artifact)
        loaded = self._artifacts.load(address)
        if loaded.code != draft.code:
            raise PaperAccountError("frozen artifact failed round-trip verification")
        account = self._repository.create_account(
            owner=actor_id,
            draft_id=draft.id,
            artifact_address=address,
            content_hash=draft.content_hash,
            market=draft.market,
            instrument_ids=tuple(draft.instrument_ids),
            frequency=draft.frequency,
            initial_cash=initial_cash or _DEFAULT_INITIAL_CASH,
        )
        # 记录「回测通过 → 发布仿真」的绑定，推动研究生命周期进入 PAPER_LINKED。
        self._drafts.record_paper_binding(
            draft_id=draft.id,
            account_id=account.id,
            published_at=datetime.now(UTC),
        )
        return account

    def get_account(self, account_id: str) -> PaperAccount | None:
        return self._repository.get_account(account_id)

    def list_accounts(self, *, owner: str | None = None) -> list[PaperAccount]:
        return self._repository.list_accounts(owner=owner)

    def transition(self, *, account_id: str, action: str) -> PaperAccount:
        account = self._repository.get_account(account_id)
        if account is None:
            raise KeyError(f"account not found: {account_id}")
        target = next_state(account.state, action)
        return self._repository.update_state(account_id, target)

    def require_active(self, account_id: str) -> PaperAccount:
        """Runtime entry point guard for the future node runner."""
        account = self.get_account(account_id)
        if account is None:
            raise KeyError(f"account not found: {account_id}")
        if account.state is not PaperAccountState.ACTIVE:
            raise PaperAccountError(
                f"account {account_id} is {account.state.value}, not ACTIVE"
            )
        return account
