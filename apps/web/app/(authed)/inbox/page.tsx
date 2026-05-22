import { ExtractionsTable } from "@/components/extraction/ExtractionsTable";
import { DocumentTable } from "@/components/inbox/document-table";
import { InboxToolbar } from "@/components/inbox/inbox-toolbar";
import { buttonVariants } from "@/components/ui/button";
import type {
  DocumentClassification,
  DocumentListFilters,
  DocumentStatus,
  UrgencyLevel,
} from "@/lib/document-types";
import { listDocuments } from "@/lib/documents";
import { listExtractions } from "@/lib/extractions";
import { cn } from "@/lib/utils";
import Link from "next/link";

interface PageProps {
  searchParams: Promise<{
    status?: string;
    classification?: string;
    urgency?: string;
    view?: string;
  }>;
}

export default async function InboxPage({ searchParams }: PageProps): Promise<React.ReactElement> {
  const sp = await searchParams;
  const view = sp.view === "needs_review" ? "needs_review" : "all";

  if (view === "needs_review") {
    const extractions = await listExtractions({ needs_review: true, limit: 100 });
    return (
      <div className="px-8 py-6">
        <header className="pb-4">
          <h1 className="font-semibold text-2xl tracking-tight">Inbox</h1>
          <p className="text-sm text-muted-foreground">
            {extractions.total} extraction{extractions.total === 1 ? "" : "s"} need
            {extractions.total === 1 ? "s" : ""} review
          </p>
        </header>
        <ViewTabs current="needs_review" />
        <ExtractionsTable items={extractions.items} />
      </div>
    );
  }

  const filters: DocumentListFilters = {};
  if (sp.status) filters.status = sp.status as DocumentStatus;
  if (sp.classification) filters.classification = sp.classification as DocumentClassification;
  if (sp.urgency) filters.urgency = sp.urgency as UrgencyLevel;

  const result = await listDocuments(filters);

  return (
    <div className="px-8 py-6">
      <header className="pb-4">
        <h1 className="font-semibold text-2xl tracking-tight">Inbox</h1>
        <p className="text-sm text-muted-foreground">
          {result.total} {result.total === 1 ? "document" : "documents"}
          {Object.keys(filters).length > 0 ? " matching filters" : ""}
        </p>
      </header>
      <ViewTabs current="all" />
      <InboxToolbar />
      <DocumentTable items={result.items} />
    </div>
  );
}

function ViewTabs({ current }: { current: "all" | "needs_review" }): React.ReactElement {
  return (
    <div className="mb-4 flex gap-1 border-b border-border">
      <Link
        href="/inbox"
        className={cn(
          buttonVariants({ variant: "ghost", size: "sm" }),
          "rounded-b-none border-b-2",
          current === "all" ? "border-primary text-foreground" : "border-transparent",
        )}
      >
        All documents
      </Link>
      <Link
        href="/inbox?view=needs_review"
        className={cn(
          buttonVariants({ variant: "ghost", size: "sm" }),
          "rounded-b-none border-b-2",
          current === "needs_review" ? "border-primary text-foreground" : "border-transparent",
        )}
      >
        Needs review
      </Link>
    </div>
  );
}
