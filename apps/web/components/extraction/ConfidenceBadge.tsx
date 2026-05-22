"use client";

import { Badge } from "@/components/ui/badge";

interface ConfidenceBadgeProps {
  score: number;
  isMissing?: boolean;
}

export function ConfidenceBadge({
  score,
  isMissing = false,
}: ConfidenceBadgeProps): React.ReactElement {
  if (isMissing) {
    return (
      <Badge variant="destructive" title="Field missing from source document">
        Missing
      </Badge>
    );
  }
  const variant = score >= 0.8 ? "success" : score >= 0.5 ? "warning" : "destructive";
  const pct = Math.round(score * 100);
  return (
    <Badge variant={variant} title={`Confidence: ${score.toFixed(2)}`}>
      {pct}%
    </Badge>
  );
}
