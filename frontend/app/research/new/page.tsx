import { Suspense } from "react";

import { StrategyChat } from "../../../components/strategy-chat";
import { getServerT } from "../../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function NewResearchPage() {
  const t = await getServerT();
  return (
    <div className="page sc-page">
      <div className="sc-page-heading">
        <span className="eyebrow">{t("newResearch.eyebrow")}</span>
        <h1>{t("newResearch.title")}</h1>
        <p className="lede">{t("newResearch.lede")}</p>
      </div>
      <Suspense fallback={null}>
        <StrategyChat />
      </Suspense>
    </div>
  );
}
