import { CallList } from "@/components/voice/call-list";
import { StartTestCallButton } from "@/components/voice/start-test-call-button";
import { listActiveCalls } from "@/lib/voice";

export default async function VoicePage(): Promise<React.ReactElement> {
  const list = await listActiveCalls();
  return (
    <div className="px-8 py-6 space-y-4">
      <header className="flex items-start justify-between gap-4 pb-2">
        <div>
          <h1 className="font-semibold text-2xl tracking-tight">Voice — Ember</h1>
          <p className="text-sm text-muted-foreground">
            Active outbound calls. v1 calls dial through a browser caller — no PSTN trunk yet (see
            ADR 010).
          </p>
        </div>
        <StartTestCallButton />
      </header>
      <CallList calls={list.items} />
    </div>
  );
}
