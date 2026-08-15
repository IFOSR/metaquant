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
from quant_platform.data_gateway.akshare_vendor import (
    AkShareMarketDataProvider,
    AkShareVendorAdapter,
)
from quant_platform.data_gateway.gateway import (
    InMemorySnapshotStore,
    PITDataGateway,
    SnapshotStore,
)
from quant_platform.data_gateway.ifind_client import (
    IFindClient,
    IFindMarketDataProvider,
    fetch_close_series,
    load_client_from_env,
    parse_date_sequence,
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
from quant_platform.data_gateway.resolver import (
    Bar,
    BarRequest,
    BarSeries,
    DataSourceExhausted,
    MarketDataProvider,
    MarketDataSourceResolver,
    default_provider_chain,
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
    "AkShareVendorAdapter",
    "AkShareMarketDataProvider",
    "ArtifactClass",
    "Bar",
    "BarRequest",
    "BarSeries",
    "CrossValidationStatus",
    "DataSourceExhausted",
    "DatasetContract",
    "FieldContract",
    "FrozenSnapshot",
    "FuturesContractChainAdapter",
    "IFindClient",
    "IFindMarketDataProvider",
    "InMemorySnapshotStore",
    "MarketDataSource",
    "MarketDataProvider",
    "MarketDataSourceResolver",
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
    "default_provider_chain",
    "fetch_close_series",
    "filter_and_resolve",
    "formal_response",
    "guard_exploratory",
    "load_client_from_env",
    "parse_date_sequence",
    "validate_pit_rows",
]
