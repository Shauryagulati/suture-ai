import { signIn } from "@/auth";
import { Button } from "@/components/ui/button";
import { Activity } from "lucide-react";
import { AuthError } from "next-auth";
import { redirect } from "next/navigation";

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}): React.ReactElement {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="w-full max-w-sm space-y-6 rounded-lg border bg-card p-8 shadow-sm">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <span className="font-semibold tracking-tight">Suture</span>
        </div>
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <LoginForm searchParams={searchParams} />
        <p className="text-xs text-muted-foreground">
          Local dev. Use a seeded account (e.g. admin@scranton-cardiology.example.com).
        </p>
      </div>
    </div>
  );
}

async function LoginForm({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}): Promise<React.ReactElement> {
  const params = await searchParams;
  const error = params.error;
  const next = params.next ?? "/";

  async function action(formData: FormData): Promise<void> {
    "use server";
    const email = formData.get("email");
    const password = formData.get("password");
    const nextHref = (formData.get("next") as string | null) ?? "/";
    try {
      await signIn("credentials", {
        email,
        password,
        redirectTo: nextHref,
      });
    } catch (err) {
      if (err instanceof AuthError) {
        redirect(`/login?error=CredentialsSignin&next=${encodeURIComponent(nextHref)}`);
      }
      throw err;
    }
  }

  return (
    <form action={action} className="space-y-4">
      <input type="hidden" name="next" value={next} />
      <div className="space-y-1">
        <label htmlFor="email" className="text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      <div className="space-y-1">
        <label htmlFor="password" className="text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoComplete="current-password"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>
      {error ? (
        <div className="rounded-md border border-destructive/50 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          Invalid email or password.
        </div>
      ) : null}
      <Button type="submit" className="w-full">
        Sign in
      </Button>
    </form>
  );
}
