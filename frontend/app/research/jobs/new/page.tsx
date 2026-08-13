import Link from "next/link";

import { ResearchJobForm } from "../../../../components/research-job-form";

export default function NewResearchJobPage() {
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href="/research/jobs">Research jobs</Link>
        <span>/</span>
        <span>New</span>
      </div>
      <div className="page-heading page-heading-compact">
        <div>
          <span className="eyebrow">Research intake / draft</span>
          <h1>Open a new research job.</h1>
          <p className="lede">
            The form is deliberately strict: a market rule left blank is a future
            source of false confidence.
          </p>
        </div>
        <div className="evidence-stamp">
          <span className="eyebrow">Contract</span>
          <strong>POST /v1/research-jobs</strong>
          <span className="mono">schema v1 · actor from session</span>
        </div>
      </div>
      <ResearchJobForm />
    </div>
  );
}
