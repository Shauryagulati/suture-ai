import { CallList } from "@/components/voice/call-list";
import { listActiveCalls } from "@/lib/voice";

export default async function VoicePage(): Promise<React.ReactElement> {
  const list = await listActiveCalls();
  return (
    <div className="px-8 py-6 space-y-4">
      <header className="pb-2">
        <h1 className="font-semibold text-2xl tracking-tight">Voice — Ember</h1>
        <p className="text-sm text-muted-foreground">
          Active outbound calls. v1 calls dial through a browser caller — no PSTN trunk yet (see ADR
          010).
        </p>
      </header>
      <CallList calls={list.items} />
    </div>
  );
}
