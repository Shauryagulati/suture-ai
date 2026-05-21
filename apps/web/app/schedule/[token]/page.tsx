// Public patient-facing scheduling page. NOT under (authed) — the
// signed token is the only credential. The handler decodes the token,
// sets the tenant ContextVar from claims, and queries mock slots.

import { BookingForm } from "./booking-form";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

interface SchedulingPayload {
  patient_first_name: string;
  slots: string[];
  outreach_attempt_id: string;
}

async function fetchSchedule(token: string): Promise<SchedulingPayload | null> {
  const r = await fetch(`${API_URL}/api/schedule/${token}`, {
    cache: "no-store",
  });
  if (!r.ok) {
    return null;
  }
  return (await r.json()) as SchedulingPayload;
}

export default async function SchedulePage({
  params,
}: {
  params: Promise<{ token: string }>;
}): Promise<React.ReactElement> {
  const { token } = await params;
  const data = await fetchSchedule(token);

  if (data === null) {
    return (
      <main className="mx-auto max-w-md p-6">
        <h1 className="text-2xl font-semibold">Link expired</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This scheduling link is no longer valid. Please call your clinic to schedule.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-md p-6">
      <h1 className="text-2xl font-semibold">Hi {data.patient_first_name}</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Pick a follow-up time below. We&apos;ll send a reminder before your appointment.
      </p>
      <div className="mt-5">
        <BookingForm
          token={token}
          slots={data.slots}
          outreachAttemptId={data.outreach_attempt_id}
        />
      </div>
    </main>
  );
}
