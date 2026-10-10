import { NextResponse, type NextRequest } from "next/server";
import { mintDevToken, type Role } from "@/lib/dev-token";
import { isSameOrigin } from "@/lib/proxy-policy";
import { COOKIE_NAME, config } from "@/lib/server-config";

export async function POST(request: NextRequest) {
  if (!config.devLoginEnabled) {
    return NextResponse.json({ error: "dev login is disabled" }, { status: 404 });
  }
  if (!isSameOrigin("POST", request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ error: "cross-origin request refused" }, { status: 403 });
  }
  const body = (await request.json().catch(() => null)) as { sub?: unknown; role?: unknown } | null;
  const sub = typeof body?.sub === "string" ? body.sub.trim() : "";
  const role: Role | null = body?.role === "admin" || body?.role === "student" ? body.role : null;
  if (!sub || sub.length > 200 || !role) {
    return NextResponse.json({ error: "sub and role (student|admin) required" }, { status: 400 });
  }
  let token: string;
  try {
    token = await mintDevToken(sub, role);
  } catch {
    return NextResponse.json({ error: "dev signing key not available" }, { status: 503 });
  }
  const res = NextResponse.json({ sub, role });
  res.cookies.set(COOKIE_NAME, token, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: config.tokenTtlSeconds,
  });
  return res;
}
