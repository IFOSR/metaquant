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

__all__ = [
    "ASharePITAdapter",
    "ActualFuturesContract",
    "ArtifactClass",
    "DatasetContract",
    "FieldContract",
    "FrozenSnapshot",
    "FuturesContractChainAdapter",
    "InMemorySnapshotStore",
    "PITDataGateway",
    "PITRow",
    "QueryPurpose",
    "SecurityStatusUnavailableError",
    "SnapshotQuery",
    "SnapshotSlice",
    "SnapshotStore",
    "SourceClass",
]
