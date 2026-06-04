"use client";

import { Input } from "@/components/ui/input";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

export function PatientSearch({ initialQuery }: { initialQuery: string }): React.ReactElement {
  const router = useRouter();
  const pathname = usePathname();
  const [q, setQ] = useState(initialQuery);

  function submit(e: React.FormEvent): void {
    e.preventDefault();
    const trimmed = q.trim();
    router.push(trimmed ? `${pathname}?q=${encodeURIComponent(trimmed)}` : pathname);
  }

  return (
    <form onSubmit={submit} className="max-w-sm">
      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search name, MRN, or city…"
        aria-label="Search patients"
      />
    </form>
  );
}
