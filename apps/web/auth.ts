import NextAuth from "next-auth";
import type { JWT } from "next-auth/jwt";
import Credentials from "next-auth/providers/credentials";

declare module "next-auth" {
  interface User {
    apiAccessToken?: string;
    apiRefreshToken?: string;
    clinicId?: string;
    role?: string;
  }
  interface Session {
    apiAccessToken?: string;
    clinicId?: string;
    role?: string;
    userId?: string;
    error?: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    apiAccessToken?: string;
    apiRefreshToken?: string;
    apiAccessTokenExpires?: number;
    clinicId?: string;
    role?: string;
    userId?: string;
    error?: string;
  }
}

// Forces TS to load the module so the augmentation above takes effect.
type _ensureJwtLoaded = JWT;

const API_URL = process.env.API_URL ?? "http://localhost:8000";

type ApiLoginResponse = {
  access_token: string;
  refresh_token: string;
  user_id: string;
  active_clinic_id: string;
  role: string;
};

type ApiMeResponse = {
  user_id: string;
  email: string;
  full_name: string;
  active_clinic_id: string;
  role: string;
};

async function refreshFromApi(refreshToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { access_token: string };
    return body.access_token;
  } catch {
    return null;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  pages: { signIn: "/login" },
  session: { strategy: "jwt" },
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email;
        const password = credentials?.password;
        if (typeof email !== "string" || typeof password !== "string") return null;

        const loginRes = await fetch(`${API_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!loginRes.ok) return null;
        const data = (await loginRes.json()) as ApiLoginResponse;

        // Fetch full profile (full_name, etc.) via /me.
        const meRes = await fetch(`${API_URL}/api/auth/me`, {
          headers: { Authorization: `Bearer ${data.access_token}` },
        });
        if (!meRes.ok) return null;
        const me = (await meRes.json()) as ApiMeResponse;

        return {
          id: me.user_id,
          email: me.email,
          name: me.full_name,
          apiAccessToken: data.access_token,
          apiRefreshToken: data.refresh_token,
          clinicId: me.active_clinic_id,
          role: me.role,
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      // Initial sign in: persist API tokens + clinic + role on the NextAuth JWT.
      if (user) {
        token.apiAccessToken = user.apiAccessToken;
        token.apiRefreshToken = user.apiRefreshToken;
        token.clinicId = user.clinicId;
        token.role = user.role;
        token.userId = user.id;
        // Access tokens last 1h; refresh ~5min before expiry to avoid races.
        token.apiAccessTokenExpires = Date.now() + 55 * 60 * 1000;
      }

      // If still valid, return as-is.
      if (
        typeof token.apiAccessTokenExpires === "number" &&
        Date.now() < token.apiAccessTokenExpires
      ) {
        return token;
      }

      // Else try to refresh via the FastAPI refresh endpoint.
      if (typeof token.apiRefreshToken === "string") {
        const newAccess = await refreshFromApi(token.apiRefreshToken);
        if (newAccess) {
          token.apiAccessToken = newAccess;
          token.apiAccessTokenExpires = Date.now() + 55 * 60 * 1000;
          return token;
        }
        // Refresh failed → invalidate session.
        return { ...token, apiAccessToken: undefined, error: "RefreshFailed" };
      }
      return token;
    },
    async session({ session, token }) {
      session.apiAccessToken = token.apiAccessToken;
      session.clinicId = token.clinicId;
      session.role = token.role;
      if (typeof token.userId === "string") session.userId = token.userId;
      session.error = token.error;
      return session;
    },
  },
});
