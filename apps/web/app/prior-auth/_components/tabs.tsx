import Link from "next/link";

export type PriorAuthTab = "check" | "tracker";

export function Tabs({ active }: { active: PriorAuthTab }): React.ReactElement {
  return (
    <div className="border-b mb-6 flex gap-6">
      <TabLink href="/prior-auth?tab=check" label="Check" active={active === "check"} />
      <TabLink href="/prior-auth?tab=tracker" label="Tracker" active={active === "tracker"} />
    </div>
  );
}

function TabLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}): React.ReactElement {
  return (
    <Link
      href={href}
      className={`py-2 -mb-px border-b-2 text-sm font-medium transition-colors ${
        active
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      {label}
    </Link>
  );
}
