import { auth } from "@/auth";
import { Sidebar } from "@/components/Sidebar";
import { ClinicProvider } from "@/components/providers/clinic-provider";
import { Toaster } from "@/components/ui/sonner";
import { redirect } from "next/navigation";

export default async function AuthedLayout({
  children,
}: {
  children: React.ReactNode;
}): Promise<React.ReactElement> {
  const session = await auth();
  if (!session?.apiAccessToken) {
    redirect("/login");
  }

  // The single QueryClient lives in the root <Providers>. Here we only
  // partition the cache by active clinic for the authed subtree.
  return (
    <ClinicProvider clinicId={session.clinicId ?? null}>
      <div className="flex h-screen w-screen overflow-hidden bg-background">
        <Sidebar />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
      <Toaster />
    </ClinicProvider>
  );
}
