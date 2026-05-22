import { BrowserCaller } from "@/components/voice/browser-caller";
import { getCallToken } from "@/lib/voice";

interface PageProps {
  params: Promise<{ callId: string }>;
}

export default async function TestCallerPage({ params }: PageProps): Promise<React.ReactElement> {
  const { callId } = await params;
  const tokenResponse = await getCallToken(callId);
  return (
    <div className="px-8 py-6 space-y-4">
      <header>
        <h1 className="font-semibold text-2xl tracking-tight">Test caller</h1>
        <p className="text-sm text-muted-foreground">
          Browser-based stand-in for a phone call. Talk to Ember directly from this page.
        </p>
      </header>
      <BrowserCaller
        livekitUrl={tokenResponse.livekit_url}
        token={tokenResponse.token}
        roomName={tokenResponse.room_name}
      />
    </div>
  );
}
