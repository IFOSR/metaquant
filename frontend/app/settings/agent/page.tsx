import { AgentConfig } from "../../../components/agent-config";
import { getServerT } from "../../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function AgentConfigPage() {
  const t = await getServerT();
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("agent.eyebrow")}</span>
          <h1>{t("agent.title")}</h1>
          <p className="lede">{t("agent.lede")}</p>
        </div>
      </div>
      <AgentConfig />
    </div>
  );
}
