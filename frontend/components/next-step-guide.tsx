import Link from "next/link";

import type { ResearchJob } from "../lib/types";

interface NextStepGuideProps {
  job: ResearchJob;
  hasBrief: boolean;
  hasFrozenBrief: boolean;
  hasExperiment: boolean;
  hasRun: boolean;
}

export function NextStepGuide({
  job,
  hasBrief,
  hasFrozenBrief,
  hasExperiment,
  hasRun,
}: NextStepGuideProps) {
  let title: string;
  let detail: string;
  let href: string | null = null;

  if (!hasBrief) {
    title = "下一步：写下你的研究假设";
    detail =
      "研究简报回答「研究什么、为什么、预期方向」。打开简报编辑器后，可以一键套用预置模板。";
    href = `/research/jobs/${job.id}/brief`;
  } else if (!hasFrozenBrief) {
    title = "下一步：冻结研究简报";
    detail = "冻结后简报版本不可修改，成为下游实验的父级产物。";
    href = `/research/jobs/${job.id}/brief`;
  } else if (!hasExperiment) {
    title = "下一步：预注册实验";
    detail = "定义具体的因子表达式（挖什么因子），并绑定冻结的简报与数据快照。";
  } else if (!hasRun) {
    title = "下一步：运行实验";
    detail = "计算因子值并执行验证门禁，产出可审计的结果。";
  } else {
    title = "实验已运行";
    detail = "查看下方验证报告，或前往策略页对通过门禁的因子做回测。";
  }

  return (
    <div className="next-step-bar">
      <div className="next-step-text">
        <span className="eyebrow">当前进度</span>
        <strong>{title}</strong>
        <span>{detail}</span>
      </div>
      {href ? (
        <Link className="button button-primary" href={href}>
          去处理
        </Link>
      ) : null}
    </div>
  );
}
