// Pure rules for the backend-for-frontend proxy. Kept free of Next imports so they
// can be unit-tested and read in one sitting.

// Only these API areas are reachable through the browser. Admin-only areas (/cache,
// /batch, /debate/multi-agent) are deliberately absent: the UI does not need them yet,
// and an allowlist fails closed when the API grows a new route.
const ALLOWED_PREFIXES = ["debate", "memory", "health"] as const;
const BLOCKED_PATHS = new Set(["debate/multi-agent"]);

export function isAllowedPath(segments: string[]): boolean {
  if (segments.length === 0) return false;
  // Dot segments or empty segments could climb out of the intended path once joined.
  if (segments.some((s) => s === "" || s === "." || s === ".." || s.includes("/") || s.includes("\\"))) {
    return false;
  }
  const joined = segments.join("/");
  if (BLOCKED_PATHS.has(joined)) return false;
  return (ALLOWED_PREFIXES as readonly string[]).includes(segments[0]);
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

// CSRF defence for cookie-authenticated, state-changing requests. SameSite=Strict on the
// cookie is the first layer; this is the second: the Origin header must equal our own.
export function isSameOrigin(method: string, origin: string | null, host: string | null): boolean {
  if (SAFE_METHODS.has(method.toUpperCase())) return true;
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}
