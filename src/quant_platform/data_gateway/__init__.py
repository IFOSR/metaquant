"""Pure point-in-time data access domain.

Formal consumers can only query immutable snapshots through PITDataGateway.
The package intentionally contains no production provider selection or raw
table access.
"""

from quant_platform.data_gateway.adapters import (
    ASharePITAdapter,
    FuturesContractChainAdapter,
    SecurityStatusUnavailableError,
)
from quant_platform.data_gateway.gateway import (
    InMemorySnapshotStore,
    PITDataGateway,
    SnapshotStore,
)
from quant_platform.data_gateway.loader import (
    CrossValidationStatus,
    MarketDataSource,
    RawPITRow,
    filter_and_resolve,
    validate_pit_rows,
)
from quant_platform.data_gateway.models import (
    ActualFuturesContract,
    ArtifactClass,
    DatasetContract,
    FieldContract,
    FrozenSnapshot,
    PITRow,
    QueryPurpose,
    SnapshotQuery,
    SnapshotSlice,
    SourceClass,
)
from quant_platform.data_gateway.vendor import (
    VendorAdapter,
    VendorResponse,
    VendorSourceClass,
    exploratory_response,
    formal_response,
    guard_exploratory,
)

__all__ = [
    "ASharePITAdapter",
    "ActualFuturesContract",
    "ArtifactClass",
    "CrossValidationStatus",
    "DatasetContract",
    "FieldContract",
    "FrozenSnapshot",
    "FuturesContractChainAdapter",
    "InMemorySnapshotStore",
    "MarketDataSource",
    "PITDataGateway",
    "PITRow",
    "QueryPurpose",
    "RawPITRow",
    "SecurityStatusUnavailableError",
    "SnapshotQuery",
    "SnapshotSlice",
    "SnapshotStore",
    "SourceClass",
    "VendorAdapter",
    "VendorResponse",
    "VendorSourceClass",
    "exploratory_response",
    "filter_and_resolve",
    "formal_response",
    "guard_exploratory",
    "validate_pit_rows",
]
