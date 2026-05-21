import { DocumentTable } from "@/components/inbox/document-table";
import { InboxToolbar } from "@/components/inbox/inbox-toolbar";
import type {
  DocumentClassification,
  DocumentListFilters,
  DocumentStatus,
  UrgencyLevel,
} from "@/lib/document-types";
import { listDocuments } from "@/lib/documents";

interface PageProps {
  searchParams: Promise<{
    status?: string;
    classification?: string;
    urgency?: string;
  }>;
}

export default async function InboxPage({ searchParams }: PageProps): Promise<React.ReactElement> {
  const sp = await searchParams;
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
      <InboxToolbar />
      <DocumentTable items={result.items} />
    </div>
  );
}
