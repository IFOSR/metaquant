import type { ResearchBrief } from "./types";

export function selectLatestBriefVersion(
  versions: ResearchBrief[],
): ResearchBrief | undefined {
  return versions.reduce<ResearchBrief | undefined>(
    (latest, candidate) =>
      latest === undefined || candidate.version > latest.version
        ? candidate
        : latest,
    undefined,
  );
}
