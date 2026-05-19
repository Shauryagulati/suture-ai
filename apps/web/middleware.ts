import { auth } from "@/auth";

// Protect everything except /login and the NextAuth route handlers.
export default auth((req) => {
  const { pathname } = req.nextUrl;
  const isLogin = pathname === "/login";
  const isApiAuth = pathname.startsWith("/api/auth");
  const isStatic =
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon") ||
    pathname.endsWith(".svg") ||
    pathname.endsWith(".png");

  if (isLogin || isApiAuth || isStatic) return undefined;

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
