import Link from "next/link";

import { BriefEditor } from "../../../../../components/brief-editor";
import { selectLatestBriefVersion } from "../../../../../lib/briefs";
import { quantApiClient } from "../../../../../lib/client";

export default async function ResearchBriefPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const versions = await quantApiClient.listBriefVersions(id);
  const brief = selectLatestBriefVersion(versions);
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href={`/research/jobs/${id}`}>ResearchJob</Link>
        <span>/</span>
        <span>Brief</span>
      </div>
      <div className="page-heading page-heading-compact">
        <div>
          <span className="eyebrow">Research brief / versioned</span>
          <h1>State the claim before you search.</h1>
          <p className="lede">
            Drafts can change. Frozen versions become the parent artifact for every
            downstream run.
          </p>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">Endpoint</span>
          <strong>PATCH /v1/research-brief-versions</strong>
          <span className="mono">If-Match + Idempotency-Key</span>
        </div>
      </div>
      {brief ? <BriefEditor initialBrief={brief} /> : null}
    </div>
  );
}
