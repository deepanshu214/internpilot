import { NextResponse, type NextRequest } from "next/server";
import { COOKIE, authEnabled, safeEqual, sessionToken } from "@/lib/auth";

export async function middleware(req: NextRequest) {
  if (!authEnabled()) {
    // Local dev without a password is fine; a deployed dashboard must never be open.
    if (process.env.NODE_ENV === "production" && !process.env.ALLOW_NO_AUTH)
      return new NextResponse("Set DASHBOARD_PASSWORD to use the deployed dashboard.", { status: 503 });
    return NextResponse.next();
  }
  if (req.nextUrl.pathname === "/login") return NextResponse.next();
  const cookie = req.cookies.get(COOKIE)?.value ?? "";
  if (cookie && safeEqual(cookie, await sessionToken())) return NextResponse.next();
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = "";
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"] };
