import { Sidebar } from "@/components/Sidebar";

export default function AnalyticsPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Analytics — Module 7 ships leakage scoring and the at-risk dashboard.
      </main>
    </div>
  );
}
