import { Activity, BarChart3, FileSearch, Inbox, ListChecks, Settings, Users } from "lucide-react";
import Link from "next/link";

const NAV_ITEMS = [
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/patients", label: "Patients", icon: Users },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/prior-auth", label: "Prior Auth", icon: FileSearch },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

export function Sidebar(): React.ReactElement {
  return (
    <aside className="flex h-screen w-60 flex-col border-r bg-card">
      <div className="flex items-center gap-2 px-6 py-5 border-b">
        <Activity className="h-5 w-5 text-primary" />
        <span className="font-semibold tracking-tight">Suture</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="px-6 py-3 text-xs text-muted-foreground border-t">v0.1.0 · local dev</div>
    </aside>
  );
}
