export function buildProxyTarget(
  upstream: string,
  path: string[],
  search: string,
) {
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  return `${upstream.replace(/\/$/, "")}/${encodedPath}${search}`;
}

export function isAllowedQuantApiPath(path: string[]) {
  if (path[0] !== "v1") return false;
  if (path[1] === "session") return path.length === 2;
  if (path[1] === "formal-snapshots") return path.length === 2;
  if (path[1] === "label-snapshots") return path.length === 2;
  if (path[1] === "data-provisioning") {
    return path.length === 2 || path.length === 3;
  }
  if (path[1] === "research-briefs:from-paper") return path.length === 2;
  if (path[1] === "experiments:preregister") return path.length === 2;
  if (path[1] === "alpha-pool") return path.length === 2;
  if (path[1] === "backtests") return path.length === 2;
  if (path[1] === "market-data") {
    return path.length === 3 && path[2] === "coverage";
  }
  if (path[1] === "execution") {
    return (
      path.length === 3 &&
      (path[2] === "state" ||
        path[2] === "kill-switch:trip" ||
        path[2] === "kill-switch:reset")
    );
  }
  if (path[1] === "experiments") {
    return (
      path.length === 3 &&
      Boolean(path[2]) &&
      (!path[2].includes(":") || path[2].endsWith(":run"))
    );
  }
  if (path[1] === "experiment-runs") {
    return (
      (path.length === 3 && Boolean(path[2])) ||
      (path.length === 4 && Boolean(path[2]) && path[3] === "artifacts")
    );
  }
  if (path[1] === "research-jobs") {
    if (path.length === 2) return true;
    if (path.length === 3) return Boolean(path[2]);
    return (
      path.length === 4 &&
      Boolean(path[2]) &&
      path[3] === "brief-versions"
    );
  }
  return (
    path[1] === "research-brief-versions" &&
    path.length === 3 &&
    Boolean(path[2]) &&
    (!path[2].includes(":") || path[2].endsWith(":freeze"))
  );
}
