"use client";

import { Card } from "@/components/ui/card";

interface MissingFieldsBannerProps {
  missingFields: string[];
}

export function MissingFieldsBanner({
  missingFields,
}: MissingFieldsBannerProps): React.ReactElement | null {
  // The extractor can list the same path twice (e.g. referring_provider.
  // practice_fax); dedupe so React keys stay unique.
  const fields = [...new Set(missingFields)];
  if (fields.length === 0) return null;
  const isParseFail = fields.length === 1 && fields[0] === "__parse_failed__";

  return (
    <Card className="border-amber-500/40 bg-amber-500/10 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">
            {isParseFail
              ? "Extraction parse failed — review the document manually"
              : `${fields.length} field${fields.length === 1 ? "" : "s"} not extracted`}
          </div>
          {!isParseFail ? (
            <ul className="mt-1 text-xs text-amber-900/80 dark:text-amber-100/80">
              {fields.slice(0, 12).map((field) => (
                <li key={field} className="font-mono">
                  • {field}
                </li>
              ))}
              {fields.length > 12 ? (
                <li className="text-amber-900/60 dark:text-amber-100/60">
                  + {fields.length - 12} more
                </li>
              ) : null}
            </ul>
          ) : null}
        </div>
      </div>
    </Card>
  );
}
