import { decodeJwt } from "jose";
import { NextResponse, type NextRequest } from "next/server";
import { COOKIE_NAME } from "@/lib/server-config";

// Display-only: reads the claims so the UI can show who is signed in. It does NOT verify
// the signature (the API does that on every call), so never use this for access decisions.
export async function GET(request: NextRequest) {
  const token = request.cookies.get(COOKIE_NAME)?.value;
  if (!token) return NextResponse.json({ signedIn: false });
  try {
    const { sub, role, exp } = decodeJwt(token);
    return NextResponse.json({ signedIn: true, sub, role, exp });
  } catch {
    return NextResponse.json({ signedIn: false });
  }
}
