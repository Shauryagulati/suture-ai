import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Props {
  score: number;
  threshold?: number;
}

export function RiskScoreBadge({ score, threshold = 70 }: Props): React.ReactElement {
  const tone =
    score >= threshold
      ? "bg-red-100 text-red-900 border-red-200"
      : score >= threshold - 20
        ? "bg-amber-100 text-amber-900 border-amber-200"
        : "bg-emerald-100 text-emerald-900 border-emerald-200";
  return <Badge className={cn("font-mono", tone)}>{score}</Badge>;
}
