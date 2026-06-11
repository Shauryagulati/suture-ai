"use client";

import { Button } from "@/components/ui/button";
import Link from "next/link";

export default function AuthedError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): React.ReactElement {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-10 text-center">
      <h2 className="text-xl font-semibold">Something went wrong</h2>
      <p className="max-w-md text-sm text-muted-foreground">
        An unexpected error occurred while loading this page. Please try again.
      </p>
      {/* Never render error.message — it can carry internal details or PHI.
          digest is an opaque, non-sensitive reference for support. */}
      {error.digest ? (
        <p className="text-xs text-muted-foreground/70">Reference: {error.digest}</p>
      ) : null}
      <div className="flex items-center gap-4">
        <Button onClick={() => reset()}>Try again</Button>
        <Link href="/inbox" className="text-sm underline">
          Back to Inbox
        </Link>
      </div>
    </div>
  );
}
