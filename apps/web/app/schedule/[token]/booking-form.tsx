"use client";

import { useState } from "react";

interface Slot {
  iso: string;
  label: string;
}

interface Confirmation {
  appointment_id: string;
  appointment_at: string;
  status: string;
}

export function BookingForm({
  token,
  slots,
  outreachAttemptId,
}: {
  token: string;
  slots: string[];
  outreachAttemptId: string;
}): React.ReactElement {
  const [picked, setPicked] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmed, setConfirmed] = useState<Confirmation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const formatted: Slot[] = slots.map((iso) => ({
    iso,
    label: new Date(iso).toLocaleString(undefined, {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }),
  }));

  async function book(): Promise<void> {
    if (!picked) {
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const r = await fetch(`/api/scheduling/${token}/book`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          slot: picked,
          appointment_type: "cardiology_followup",
        }),
      });
      if (!r.ok) {
        setError(`Booking failed (${r.status}). Please call the clinic.`);
        return;
      }
      const body = (await r.json()) as Confirmation;
      setConfirmed(body);
    } finally {
      setSubmitting(false);
    }
  }

  if (confirmed) {
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
        <p className="text-sm font-medium text-emerald-900">You&apos;re booked.</p>
        <p className="mt-1 text-sm text-emerald-900">
          {new Date(confirmed.appointment_at).toLocaleString()}
        </p>
        <p className="mt-2 text-xs text-emerald-800">
          Confirmation #{confirmed.appointment_id.slice(0, 8)} · We&apos;ll send a reminder
          the day before.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-3" data-attempt={outreachAttemptId}>
      <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {formatted.map((slot) => {
          const selected = picked === slot.iso;
          return (
            <li key={slot.iso}>
              <button
                type="button"
                onClick={() => setPicked(slot.iso)}
                className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                  selected
                    ? "border-primary bg-primary/5"
                    : "border-border hover:border-muted-foreground/40"
                }`}
              >
                {slot.label}
              </button>
            </li>
          );
        })}
      </ul>
      <button
        type="button"
        disabled={!picked || submitting}
        onClick={book}
        className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
      >
        {submitting ? "Booking…" : "Confirm this time"}
      </button>
      {error ? <p className="text-sm text-red-600">{error}</p> : null}
    </div>
  );
}
