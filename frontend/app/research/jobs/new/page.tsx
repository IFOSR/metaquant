import Link from "next/link";

import { ResearchJobForm } from "../../../../components/research-job-form";
import { getServerT } from "../../../../lib/server-locale";

export default async function NewResearchJobPage() {
  const t = await getServerT();
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href="/research/jobs">{t("jobNew.breadcrumbJobs")}</Link>
        <span>/</span>
        <span>{t("jobNew.breadcrumbNew")}</span>
      </div>
      <div className="page-heading page-heading-compact">
        <div>
          <span className="eyebrow">{t("jobNew.eyebrow")}</span>
          <h1>{t("jobNew.title")}</h1>
          <p className="lede">
            {t("jobNew.lede")}
          </p>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">{t("jobNew.contractEyebrow")}</span>
          <strong>POST /v1/research-jobs</strong>
          <span className="mono">{t("jobNew.contractNote")}</span>
        </div>
      </div>
      <ResearchJobForm />
    </div>
  );
}
