import Link from "next/link";

import { BriefEditor } from "../../../../../components/brief-editor";
import { CreateBriefPanel } from "../../../../../components/create-brief-panel";
import { selectLatestBriefVersion } from "../../../../../lib/briefs";
import { quantApiClient } from "../../../../../lib/client";
import { getServerT } from "../../../../../lib/server-locale";

export default async function ResearchBriefPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = await getServerT();
  const { id } = await params;
  const versions = await quantApiClient.listBriefVersions(id);
  const brief = selectLatestBriefVersion(versions);
  const job = brief ? null : await quantApiClient.getResearchJob(id);
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href={`/research/jobs/${id}`}>{t("briefPage.breadcrumbJob")}</Link>
        <span>/</span>
        <span>{t("briefPage.breadcrumbBrief")}</span>
      </div>
      <div className="page-heading page-heading-compact">
        <div>
          <span className="eyebrow">{t("briefPage.eyebrow")}</span>
          <h1>{t("briefPage.title")}</h1>
          <p className="lede">
            {t("briefPage.lede")}
          </p>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">{t("briefPage.endpointEyebrow")}</span>
          <strong>PATCH /v1/research-brief-versions</strong>
          <span className="mono">If-Match + Idempotency-Key</span>
        </div>
      </div>
      {brief ? (
        <BriefEditor initialBrief={brief} />
      ) : (
        <CreateBriefPanel jobId={id} jobVersion={Number(job?.version ?? "1")} />
      )}
    </div>
  );
}
