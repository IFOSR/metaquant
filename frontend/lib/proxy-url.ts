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
  if (path[1] === "research-briefs:extract-factor") return path.length === 2;
  if (path[1] === "research-pipelines:from-paper") return path.length === 2;
  if (path[1] === "research-pipelines:from-paper-file") return path.length === 2;
  if (path[1] === "experiments:preregister") return path.length === 2;
  if (path[1] === "alpha-pool") return path.length === 2;
  if (path[1] === "backtests") return path.length === 2;
  if (path[1] === "factor-build-specs:extract") return path.length === 2;
  if (path[1] === "factor-build-specs:generate") return path.length === 2;
  if (path[1] === "factor-build-specs:smoke") return path.length === 2;
  if (path[1] === "factor-build-specs:train") return path.length === 2;
  if (path[1] === "factor-build-specs:infer") return path.length === 2;
  if (path[1] === "factor-build-specs:validate") return path.length === 2;
  if (path[1] === "factor-build-specs") {
    if (path.length === 2) return true;
    return (
      path.length === 3 &&
      Boolean(path[2]) &&
      (path[2].endsWith(":freeze") || path[2].endsWith(":generate"))
    );
  }
  if (path[1] === "factor-build-runs") {
    return path.length === 3 && Boolean(path[2]);
  }
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
  if (path[1] === "agent-config") {
    return path.length === 2 || path.length === 3;
  }
  if (path[1] === "strategy-drafts") {
    if (path.length === 2) return true;
    if (path.length === 3 && Boolean(path[2])) {
      if (!path[2].includes(":")) return true;
      return [
        ":freeze",
        ":unfreeze",
        ":save",
        ":backtest",
        ":code-test",
        ":paper",
        ":provision",
      ].some((suffix) => path[2].endsWith(suffix));
    }
    if (path.length === 4 && Boolean(path[2]) && Boolean(path[3])) {
      if (path[3] === "backtests") return true;
      return (
        path[3] === "messages" ||
        path[3] === "data-status" ||
        path[3] === "attachments"
      );
    }
    return (
      path.length === 5 &&
      Boolean(path[2]) &&
      path[3] === "backtests" &&
      Boolean(path[4])
    );
  }
  if (path[1] === "strategy-backtests" || path[1] === "strategy-backtests:matrix") {
    if (path.length === 2) return true;
    return path.length === 3 && Boolean(path[2]);
  }
  if (path[1] === "paper") {
    if (path[2] !== "accounts" || path.length < 3) return false;
    if (path.length === 3) return true;
    if (path.length === 4 && Boolean(path[3])) {
      if (path[3].includes(":")) {
        return [":pause", ":resume", ":close", ":start-node", ":stop-node"].some(
          (suffix) => path[3].endsWith(suffix),
        );
      }
      return true;
    }
    if (path.length === 5 && Boolean(path[3])) {
      return [
        "orders",
        "fills",
        "positions",
        "equity",
        "drift",
        "run-status",
      ].includes(path[4]);
    }
    return false;
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
