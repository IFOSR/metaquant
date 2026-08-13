function forwardedHosts(headers: Headers): string[] {
  const hosts: string[] = [];
  const xForwardedHost = headers.get("x-forwarded-host");
  if (xForwardedHost) {
    hosts.push(...xForwardedHost.split(",").map((value) => value.trim()));
  }

  const forwarded = headers.get("forwarded");
  if (forwarded) {
    const pattern = /(?:^|[;,])\s*host=(?:"([^"]+)"|([^;,\s]+))/gi;
    for (const match of forwarded.matchAll(pattern)) {
      hosts.push(match[1] ?? match[2]);
    }
  }
  return hosts;
}

function hostname(authority: string): string | undefined {
  try {
    return new URL(`http://${authority}`).hostname.toLowerCase();
  } catch {
    return undefined;
  }
}

function isLoopbackAuthority(authority: string): boolean {
  const host = hostname(authority);
  if (!host) return false;
  if (host === "localhost" || host === "[::1]") return true;
  const octets = host.split(".");
  return (
    octets.length === 4 &&
    octets.every((octet) => /^\d+$/.test(octet) && Number(octet) <= 255) &&
    Number(octets[0]) === 127
  );
}

export function isLocalDemoRequest(headers: Headers): boolean {
  const host = headers.get("host");
  if (!host || !isLoopbackAuthority(host)) return false;
  return forwardedHosts(headers).every(isLoopbackAuthority);
}
