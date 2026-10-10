import { NextResponse, type NextRequest } from "next/server";
import { isSameOrigin } from "@/lib/proxy-policy";
import { COOKIE_NAME } from "@/lib/server-config";

export async function POST(request: NextRequest) {
  if (!isSameOrigin("POST", request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ error: "cross-origin request refused" }, { status: 403 });
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.delete(COOKIE_NAME);
  return res;
}
