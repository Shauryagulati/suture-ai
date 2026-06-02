import { apiFetch } from "@/lib/api";
import { CheckForm } from "./_components/check-form";
import { type PriorAuthTab, Tabs } from "./_components/tabs";
import { TrackerList } from "./_components/tracker-list";
import type { PriorAuthRow } from "./types";

type SearchParams = Promise<{ tab?: string }>;

async function loadList(): Promise<PriorAuthRow[]> {
  const resp = await apiFetch("/api/prior-auth/");
  if (!resp.ok) return [];
  return (await resp.json()) as PriorAuthRow[];
}

export default async function PriorAuthPage({
  searchParams,
}: {
  searchParams: SearchParams;
}): Promise<React.ReactElement> {
  const params = await searchParams;
  const tab: PriorAuthTab = params.tab === "tracker" ? "tracker" : "check";
  const rows = tab === "tracker" ? await loadList() : [];

  return (
    <div className="p-8 max-w-7xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Prior Authorization</h1>
        <p className="text-sm text-muted-foreground">
          Payer-rules RAG over Highmark, UPMC, Aetna, Cigna, and UHC. Hybrid structured + vector
          search → LLM synthesis.
        </p>
      </header>
      <Tabs active={tab} />
      {tab === "check" ? <CheckForm /> : <TrackerList rows={rows} />}
    </div>
  );
}
