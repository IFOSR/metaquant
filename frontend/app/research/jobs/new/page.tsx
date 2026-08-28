import { PaperPipeline } from "../../../../components/paper-pipeline";
import { ResearchJobForm } from "../../../../components/research-job-form";
import { getServerT } from "../../../../lib/server-locale";

export const dynamic = "force-dynamic";

export default async function NewResearchJobPage() {
  const t = await getServerT();
  return (
    <div className="page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">{t("jobs.newEyebrow")}</span>
          <h1>{t("jobs.newTitle")}</h1>
          <p className="lede">{t("jobs.newLede")}</p>
        </div>
      </div>
      <ResearchJobForm />
      <PaperPipeline />
    </div>
  );
}
