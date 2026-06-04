import {
  Activity,
  BarChart3,
  FileSearch,
  Gauge,
  Inbox,
  ListChecks,
  PhoneCall,
  Send,
  Settings,
  Users,
} from "lucide-react";
import Link from "next/link";

import { AtRiskSidebarBadge } from "@/components/analytics/at-risk-sidebar-badge";
import { Badge } from "@/components/ui/badge";
import { listExtractions } from "@/lib/extractions";

const NAV_ITEMS = [
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/patients", label: "Patients", icon: Users },
  { href: "/tasks", label: "Tasks", icon: ListChecks },
  { href: "/outreach", label: "Outreach", icon: Send },
  { href: "/prior-auth", label: "Prior Auth", icon: FileSearch },
  { href: "/voice", label: "Voice", icon: PhoneCall },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/analytics/evals", label: "Evals", icon: Gauge },
  { href: "/settings", label: "Settings", icon: Settings },
] as const;

async function getNeedsReviewCount(): Promise<number> {
  try {
    const result = await listExtractions({ needs_review: true, limit: 1 });
    return result.total;
  } catch {
    return 0;
  }
}

export async function Sidebar(): Promise<React.ReactElement> {
  const needsReviewCount = await getNeedsReviewCount();
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
            className="flex items-center justify-between gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <span className="flex items-center gap-3">
              <Icon className="h-4 w-4" />
              {label}
            </span>
            {label === "Inbox" && needsReviewCount > 0 ? (
              <Badge variant="destructive" className="h-5 px-1.5 text-[10px]">
                {needsReviewCount}
              </Badge>
            ) : null}
            {href === "/analytics" ? <AtRiskSidebarBadge /> : null}
          </Link>
        ))}
      </nav>
      <div className="px-6 py-3 text-xs text-muted-foreground border-t">v0.1.0 · local dev</div>
    </aside>
  );
}
