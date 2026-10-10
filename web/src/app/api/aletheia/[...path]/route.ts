import { NextResponse, type NextRequest } from "next/server";
import { isAllowedPath, isSameOrigin } from "@/lib/proxy-policy";
import { COOKIE_NAME, config } from "@/lib/server-config";

// Backend-for-frontend proxy. The browser holds only an httpOnly session cookie; this
// handler turns it into an Authorization header for FastAPI. The token never reaches
// page JavaScript, so an XSS bug cannot read it.
async function handle(request: NextRequest, ctx: RouteContext<"/api/aletheia/[...path]">) {
  const { path } = await ctx.params;
  if (!isAllowedPath(path)) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  if (!isSameOrigin(request.method, request.headers.get("origin"), request.headers.get("host"))) {
    return NextResponse.json({ error: "cross-origin request refused" }, { status: 403 });
  }

  const token = request.cookies.get(COOKIE_NAME)?.value;
  const url = `${config.apiUrl}/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`;
  const headers = new Headers({ accept: "application/json" });
  if (token) headers.set("authorization", `Bearer ${token}`);
  const hasBody = !["GET", "HEAD"].includes(request.method);
  if (hasBody) headers.set("content-type", request.headers.get("content-type") ?? "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? await request.text() : undefined,
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: "API unreachable" }, { status: 502 });
  }

  // Pass status and body through; forward nothing else (no Set-Cookie from upstream).
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export { handle as GET, handle as POST, handle as DELETE };
