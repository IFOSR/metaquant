import { BacktestWorkbench } from "../../components/backtest-workbench";
import { getServerT } from "../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function BacktestPage() {
  const t = await getServerT();
  return (
    <div className="page bt-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("backtest.eyebrow")}</span>
          <h1>{t("backtest.title")}</h1>
          <p className="lede">{t("backtest.lede")}</p>
        </div>
      </div>
      <BacktestWorkbench />
    </div>
  );
}
