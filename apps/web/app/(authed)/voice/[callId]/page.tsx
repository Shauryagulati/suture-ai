import Link from "next/link";

import { auth } from "@/auth";
import { Badge } from "@/components/ui/badge";
import { EndCallButton } from "@/components/voice/end-call-button";
import { TranscriptStream } from "@/components/voice/transcript-stream";
import { getCallById, getCallTranscript } from "@/lib/voice";

interface PageProps {
  params: Promise<{ callId: string }>;
}

export default async function VoiceCallPage({ params }: PageProps): Promise<React.ReactElement> {
  const { callId } = await params;
  const session = await auth();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const [call, persisted] = await Promise.all([getCallById(callId), getCallTranscript(callId)]);

  const isActive =
    call !== null && !["completed", "failed", "no_answer", "voicemail"].includes(call.status);

  return (
    <div className="flex h-full flex-col">
      <header className="border-b px-8 py-4 flex items-center justify-between">
        <div>
          <Link href="/voice" className="text-xs text-muted-foreground hover:underline">
            ← Back to active calls
          </Link>
          <h1 className="font-semibold text-xl tracking-tight mt-1">
            Call <span className="font-mono text-base">{callId.slice(0, 8)}…</span>
          </h1>
        </div>
        <div className="flex items-center gap-3">
          {call ? <Badge>{call.status}</Badge> : null}
          {isActive ? <EndCallButton callId={callId} /> : null}
          {isActive ? (
            <Link
              href={`/voice/test-caller/${callId}`}
              className="text-sm text-primary hover:underline"
              target="_blank"
              rel="noreferrer"
            >
              Open test caller →
            </Link>
          ) : null}
        </div>
      </header>

      <div className="grid flex-1 grid-cols-3 gap-6 px-8 py-6 overflow-hidden">
        <div className="col-span-2 min-h-0">
          {isActive && session?.apiAccessToken ? (
            <TranscriptStream
              apiBaseUrl={apiBaseUrl}
              callId={callId}
              accessToken={session.apiAccessToken}
            />
          ) : persisted ? (
            <div className="rounded-md border bg-card p-6 space-y-3">
              <h2 className="font-medium">Persisted transcript</h2>
              <pre className="whitespace-pre-wrap font-mono text-xs text-foreground">
                {persisted.full_transcript}
              </pre>
            </div>
          ) : (
            <div className="rounded-md border bg-card p-8 text-center text-sm text-muted-foreground">
              No transcript yet.
            </div>
          )}
        </div>
        <aside className="space-y-3">
          <div className="rounded-md border bg-card p-4 space-y-2">
            <h3 className="text-sm font-medium">Call info</h3>
            {call ? (
              <dl className="text-xs space-y-1">
                <Row label="Patient">
                  <span className="font-mono">{call.patient_id.slice(0, 8)}…</span>
                </Row>
                <Row label="Type">{call.call_type}</Row>
                <Row label="Started">{new Date(call.started_at).toLocaleString()}</Row>
                {call.ended_at ? (
                  <Row label="Ended">{new Date(call.ended_at).toLocaleString()}</Row>
                ) : null}
              </dl>
            ) : (
              <p className="text-xs text-muted-foreground">Call not found in active list.</p>
            )}
          </div>
          <div className="rounded-md border border-dashed bg-card p-4 text-xs text-muted-foreground">
            Playback coming in v2 — call audio is not stored.
          </div>
        </aside>
      </div>
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
