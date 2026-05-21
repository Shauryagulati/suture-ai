import { Sidebar } from "@/components/Sidebar";

export default function SettingsPage(): React.ReactElement {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 p-10 text-muted-foreground">
        Settings — clinic config, user management, outreach cadence rules.
      </main>
    </div>
  );
}
