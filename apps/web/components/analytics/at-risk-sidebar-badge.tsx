import { getLeakage } from "@/lib/analytics";

export async function AtRiskSidebarBadge(): Promise<React.ReactElement | null> {
  try {
    const data = await getLeakage();
    if (data.at_risk_count === 0) return null;
    return (
      <span className="ml-auto inline-flex items-center justify-center rounded-full bg-red-600 text-white text-[10px] font-semibold min-w-[1.25rem] h-5 px-1">
        {data.at_risk_count}
      </span>
    );
  } catch {
    return null;
  }
}
