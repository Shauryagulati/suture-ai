"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

interface EndCallButtonProps {
  callId: string;
}

export function EndCallButton({ callId }: EndCallButtonProps): React.ReactElement {
  const [pending, setPending] = useState(false);
  const router = useRouter();

  const handleClick = async () => {
    if (pending) return;
    if (!window.confirm("End this call now? The agent will hang up and the room will close.")) {
      return;
    }
    setPending(true);
    try {
      const res = await fetch(`/api/voice/end?callId=${encodeURIComponent(callId)}`, {
        method: "POST",
      });
      if (!res.ok) {
        toast.error(`Failed to end call: ${res.status}`);
        return;
      }
      toast.success("Call ended.");
      router.refresh();
    } catch (e) {
      toast.error(`Failed to end call: ${e}`);
    } finally {
      setPending(false);
    }
  };

  return (
    <Button variant="destructive" onClick={handleClick} disabled={pending}>
      {pending ? "Ending…" : "End call"}
    </Button>
  );
}
