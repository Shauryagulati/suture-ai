"use client";

import {
  type AuthDetermination,
  CPT_OPTIONS,
  PAYER_OPTIONS,
} from "@/app/(authed)/prior-auth/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, ShieldAlert } from "lucide-react";
import { useState } from "react";

export function CheckForm(): React.ReactElement {
  const [payer, setPayer] = useState<string>(PAYER_OPTIONS[0]);
  const [selectedCpts, setSelectedCpts] = useState<string[]>([]);
  const [icdInput, setIcdInput] = useState("");
  const [clinicalSummary, setClinicalSummary] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AuthDetermination | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleCpt(code: string): void {
    setSelectedCpts((cur) => (cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code]));
  }

  async function onSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setResult(null);
    if (selectedCpts.length === 0) {
      setError("Pick at least one CPT code.");
      return;
    }
    const diagnosisCodes = icdInput
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    setSubmitting(true);
    try {
      const resp = await fetch("/api/prior-auth/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          payer_name: payer,
          procedure_codes: selectedCpts,
          diagnosis_codes: diagnosisCodes,
          clinical_summary: clinicalSummary || null,
        }),
      });
      if (!resp.ok) {
        setError(`Server returned ${resp.status}: ${await resp.text()}`);
        return;
      }
      const body = (await resp.json()) as AuthDetermination;
      setResult(body);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Check prior authorization</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label htmlFor="payer" className="text-sm font-medium">
                Payer
              </label>
              <select
                id="payer"
                value={payer}
                onChange={(e) => setPayer(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              >
                {PAYER_OPTIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <span className="text-sm font-medium">Procedure (CPT)</span>
              <div className="space-y-1.5">
                {CPT_OPTIONS.map(({ code, label }) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedCpts.includes(code)}
                      onChange={() => toggleCpt(code)}
                    />
                    <span>{label}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="icd" className="text-sm font-medium">
                Diagnosis ICD-10 (comma or space separated)
              </label>
              <input
                id="icd"
                value={icdInput}
                onChange={(e) => setIcdInput(e.target.value)}
                placeholder="I25.10, R07.9"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor="summary" className="text-sm font-medium">
                Clinical summary (optional)
              </label>
              <textarea
                id="summary"
                value={clinicalSummary}
                onChange={(e) => setClinicalSummary(e.target.value)}
                rows={3}
                placeholder="65 y/o male with stable angina; abnormal stress test 2026-03"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
              />
            </div>

            <Button type="submit" disabled={submitting}>
              {submitting ? "Checking…" : "Check auth requirement"}
            </Button>
            {error && <p className="text-sm text-destructive">{error}</p>}
          </form>
        </CardContent>
      </Card>

      <div>{result && <DeterminationResult determination={result} />}</div>
    </div>
  );
}

function DeterminationResult({
  determination,
}: {
  determination: AuthDetermination;
}): React.ReactElement {
  const ar = determination.auth_required;
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          {ar ? (
            <ShieldAlert className="h-6 w-6 text-amber-600" />
          ) : (
            <CheckCircle2 className="h-6 w-6 text-emerald-600" />
          )}
          <CardTitle className="text-lg">
            {ar ? "Prior auth REQUIRED" : "Prior auth NOT required"}
          </CardTitle>
        </div>
        <p className="text-xs text-muted-foreground">
          Confidence {(determination.confidence * 100).toFixed(0)}%
          {determination.typical_turnaround_days !== null
            ? ` • Typical turnaround: ${determination.typical_turnaround_days} business days`
            : ""}
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <section>
          <h3 className="text-sm font-medium mb-1">Reasoning</h3>
          <p className="text-sm text-muted-foreground">{determination.reasoning}</p>
        </section>

        {determination.required_documents.length > 0 && (
          <section>
            <h3 className="text-sm font-medium mb-1">Required documents</h3>
            <ul className="text-sm space-y-1">
              {determination.required_documents.map((doc) => (
                <li key={doc} className="flex items-start gap-2">
                  <span aria-hidden="true">☐</span>
                  <span>{doc}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {determination.relevant_policy_excerpts.length > 0 && (
          <section>
            <h3 className="text-sm font-medium mb-1">Relevant policy excerpts</h3>
            <div className="space-y-3">
              {determination.relevant_policy_excerpts.map((exc, idx) => (
                <blockquote
                  key={`${exc.payer_name}-${exc.procedure_code}-${idx}`}
                  className="border-l-2 border-muted pl-3 text-sm"
                >
                  <p className="font-medium text-xs text-muted-foreground mb-1">
                    {exc.payer_name}, CPT {exc.procedure_code}
                    {exc.distance !== null ? ` (distance ${exc.distance.toFixed(3)})` : ""}
                  </p>
                  <p className="text-muted-foreground whitespace-pre-wrap">
                    {exc.text.slice(0, 400)}
                    {exc.text.length > 400 ? "…" : ""}
                  </p>
                </blockquote>
              ))}
            </div>
          </section>
        )}

        {determination.common_denial_reasons.length > 0 && (
          <section>
            <h3 className="text-sm font-medium mb-1">Common denial reasons (pre-empt these)</h3>
            <ul className="text-sm space-y-1 list-disc pl-5 text-muted-foreground">
              {determination.common_denial_reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </section>
        )}
      </CardContent>
    </Card>
  );
}
