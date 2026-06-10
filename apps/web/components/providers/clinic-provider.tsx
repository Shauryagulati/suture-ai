"use client";

import { type ReactNode, createContext, useContext } from "react";

const ClinicContext = createContext<string | null>(null);

export function ClinicProvider({
  clinicId,
  children,
}: {
  clinicId: string | null;
  children: ReactNode;
}): React.ReactElement {
  return <ClinicContext.Provider value={clinicId}>{children}</ClinicContext.Provider>;
}

/**
 * Active clinic id for the session (or null). Include it in every TanStack
 * query key so that when in-session clinic switching ships, clinic A's cached
 * data is never served to clinic B (the cache is partitioned per clinic).
 */
export function useActiveClinicId(): string | null {
  return useContext(ClinicContext);
}
