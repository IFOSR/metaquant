import type {
  BriefDraftInput,
  CreateResearchJobInput,
  MarketId,
} from "./types";

export interface ResearchTemplate {
  id: string;
  name: string;
  description: string;
  market: MarketId;
  job: CreateResearchJobInput;
  brief: BriefDraftInput;
  factorIr: Record<string, unknown>;
}

function futuresJob(): CreateResearchJobInput {
  return {
    market: "CN_COMMODITY_FUTURES",
    environment: "RESEARCH",
    universeRef: "futures:liquid-initial",
    frequency: "1d",
    decisionClock: "T close",
    tradeClock: "T+1 open",
    settlementClock: "T+1 settlement",
    exchangeScope: ["SHFE"],
    contractSelection: "ACTUAL_CONTRACTS_ONLY",
    rollPolicy: "roll-policy://oi-confirmed-3d/v1",
    horizon: "5 trading days",
    briefVersionId: "placeholder-brief",
  };
}

function cnAJob(): CreateResearchJobInput {
  return {
    market: "CN_A",
    environment: "RESEARCH",
    universeRef: "cn-a:main-board",
    frequency: "1d",
    decisionClock: "T close",
    tradeClock: "T+1 open",
    settlementClock: "",
    exchangeScope: [],
    contractSelection: "",
    rollPolicy: "",
    horizon: "5 trading days",
    briefVersionId: "placeholder-brief",
  };
}

function returnsExpression(periods: number) {
  return {
    op: "returns",
    args: [{ ref: "close" }],
    params: { periods },
  };
}

function futuresFactorIr(
  factorId: string,
  periods: number,
): Record<string, unknown> {
  return {
    schema_version: "factor-ir/v1",
    factor_id: factorId,
    version: "1.0.0",
    market_scope: {
      market: "CN_COMMODITY_FUTURES",
      frequency: "1d",
      universe_ref: "universe://cn-commodity-liquid-pit/v1",
      exchange_scope: ["SHFE", "INE", "DCE", "CZCE", "GFEX"],
      contract_chain_ref: "chain://commodity/main-volume-pit/v1",
      roll_policy_ref: "policy://roll/volume-no-future/v1",
    },
    decision_clock: {
      signal_time: "T_CLOSE+30m",
      earliest_trade_time: "T+1_OPEN",
    },
    inputs: [
      {
        alias: "close",
        field_ref: "market.eod.close",
        data_type: "ScalarSeries",
        unit: "CNY",
        available_time_rule: "T_CLOSE+20m",
      },
    ],
    expression: returnsExpression(periods),
    validation_policy_ref: "policy://cn-commodity-daily-factor/v1",
  };
}

function cnAFactorIr(factorId: string, periods: number): Record<string, unknown> {
  return {
    schema_version: "factor-ir/v1",
    factor_id: factorId,
    version: "1.0.0",
    market_scope: {
      market: "CN_A",
      frequency: "1d",
      universe_ref: "universe://csi300-pit/v1",
    },
    decision_clock: {
      signal_time: "T_CLOSE+30m",
      earliest_trade_time: "T+1_OPEN",
    },
    inputs: [
      {
        alias: "close",
        field_ref: "market.eod.close_adjusted",
        data_type: "ScalarSeries",
        unit: "CNY",
        available_time_rule: "T_CLOSE+20m",
      },
    ],
    expression: returnsExpression(periods),
    validation_policy_ref: "policy://cn-a-daily-factor/v1",
  };
}

function brief(
  hypothesis: string,
  economicMechanism: string,
  expectedDirection: BriefDraftInput["expectedDirection"],
  falsification: string,
  uncertainties: string,
): BriefDraftInput {
  return {
    hypothesis,
    economicMechanism,
    expectedDirection,
    falsificationConditions: [falsification],
    allowedDataDomains: ["formal.market.eod"],
    forbiddenDataDomains: [],
    constraints: ["仅覆盖历史可追溯的主板/主力合约"],
    evidenceRefIds: [],
    uncertainties: [uncertainties],
  };
}

export const RESEARCH_TEMPLATES: ResearchTemplate[] = [
  {
    id: "futures-momentum",
    name: "商品期货 5 日动量",
    description: "过去 5 日上涨的合约，未来倾向于继续上涨",
    market: "CN_COMMODITY_FUTURES",
    job: futuresJob(),
    brief: brief(
      "过去 5 日累计上涨的商品期货合约，未来 5 日收益倾向于继续为正。",
      "趋势追随资金推动价格惯性，商品供需叙事强化趋势。",
      "POSITIVE",
      "过去 5 日收益与未来 5 日收益的横截面秩相关不显著为正。",
      "动量在震荡市中可能失效，出现反转。",
    ),
    factorIr: futuresFactorIr("classic.cn_futures.momentum_5d", 5),
  },
  {
    id: "futures-reversal",
    name: "商品期货 5 日反转",
    description: "过去 5 日上涨过快的合约，未来倾向于回落",
    market: "CN_COMMODITY_FUTURES",
    job: futuresJob(),
    brief: brief(
      "过去 5 日累计上涨过快的商品期货合约，未来 5 日收益倾向于回落。",
      "短期超买后的获利回吐与均值回归。",
      "NEGATIVE",
      "过去 5 日收益与未来 5 日收益的横截面秩相关不显著为负。",
      "反转效应可能被强趋势行情压制。",
    ),
    factorIr: futuresFactorIr("classic.cn_futures.reversal_5d", 5),
  },
  {
    id: "cn-a-momentum",
    name: "A 股 5 日动量",
    description: "过去 5 日上涨的股票，未来倾向于继续上涨",
    market: "CN_A",
    job: cnAJob(),
    brief: brief(
      "过去 5 日累计上涨的 A 股股票，未来 5 日收益倾向于继续为正。",
      "信息渐进扩散与趋势追随者惯性，推动强势股价格短期延续。",
      "POSITIVE",
      "过去 5 日收益与未来 5 日收益的横截面秩相关不显著为正。",
      "动量在震荡市中可能失效，出现反转。",
    ),
    factorIr: cnAFactorIr("classic.cn_a.momentum_5d", 5),
  },
  {
    id: "cn-a-reversal",
    name: "A 股 5 日反转",
    description: "过去 5 日上涨过快的股票，未来倾向于回落",
    market: "CN_A",
    job: cnAJob(),
    brief: brief(
      "过去 5 日累计上涨过快的 A 股股票，未来 5 日收益倾向于回落。",
      "短期超买后的均值回归，投资者过度反应被修正。",
      "NEGATIVE",
      "过去 5 日收益与未来 5 日收益的横截面秩相关不显著为负。",
      "反转效应可能被强趋势行情压制。",
    ),
    factorIr: cnAFactorIr("classic.cn_a.reversal_5d", 5),
  },
];
