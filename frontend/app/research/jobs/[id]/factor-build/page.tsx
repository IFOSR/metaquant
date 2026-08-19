import Link from "next/link";

import { FactorBuildPanel } from "../../../../../components/factor-build-panel";
import { quantApiClient } from "../../../../../lib/client";

export const dynamic = "force-dynamic";

export default async function FactorBuildPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const job = await quantApiClient.getResearchJob(id);
  return (
    <div className="page">
      <div className="breadcrumb">
        <Link href="/research/jobs">研究任务</Link>
        <span>/</span>
        <Link href={`/research/jobs/${id}`}>{id}</Link>
        <span>/</span>
        <span className="mono">因子构建</span>
      </div>
      <div className="page-heading">
        <div>
          <span className="eyebrow">因子构建 / {job.market}</span>
          <h1>{job.title}</h1>
          <p className="lede">研报 → 构建规格 → 可执行代码 → 训练/推理/验证。</p>
        </div>
      </div>
      <FactorBuildPanel market={job.market} />
    </div>
  );
}
