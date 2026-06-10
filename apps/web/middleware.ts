import { auth } from "@/auth";

// Protect everything except /login, the NextAuth route handlers, and the
// public patient-scheduling flow (the signed token in the URL is the only
// credential — these pages are reached by logged-out patients from an
// SMS/email link, so they must NOT bounce to /login).
export default auth((req) => {
  const { pathname } = req.nextUrl;
  const isLogin = pathname === "/login";
  const isApiAuth = pathname.startsWith("/api/auth");
  const isPublicScheduling =
    pathname.startsWith("/schedule") || pathname.startsWith("/api/scheduling");
  const isStatic =
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.endsWith(".svg") ||
    pathname.endsWith(".png");

  if (isLogin || isApiAuth || isPublicScheduling || isStatic) return undefined;

  if (!req.auth) {
    const loginUrl = new URL("/login", req.nextUrl.origin);
    loginUrl.searchParams.set("next", pathname);
    return Response.redirect(loginUrl);
  }
  return undefined;
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
