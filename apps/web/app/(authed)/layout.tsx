import { auth } from "@/auth";
import { Sidebar } from "@/components/Sidebar";
import { QueryProvider } from "@/components/providers/query-provider";
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

  return (
    <QueryProvider>
      <div className="flex h-screen w-screen overflow-hidden bg-background">
        <Sidebar />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
      <Toaster />
    </QueryProvider>
  );
}
