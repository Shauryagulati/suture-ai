import { DocumentMetaPanel } from "@/components/inbox/document-meta-panel";
import { PdfViewer } from "@/components/inbox/pdf-viewer";
import { buttonVariants } from "@/components/ui/button";
import { getDocument } from "@/lib/documents";
import { ChevronLeft, FileSearch } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

interface PageProps {
  params: Promise<{ id: string }>;
}

const EXTRACTION_READY: ReadonlySet<string> = new Set(["extracted", "reviewed"]);

export default async function DocumentDetailPage({
  params,
}: PageProps): Promise<React.ReactElement> {
  const { id } = await params;

  const document = await getDocument(id).catch(() => null);
  if (!document) {
    notFound();
  }

  const hasExtraction = EXTRACTION_READY.has(document.status);

  return (
    <div className="flex h-screen flex-col px-6 py-4">
      <div className="flex items-center justify-between pb-3">
        <Link href="/inbox" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ChevronLeft className="mr-1 h-4 w-4" />
          Back to inbox
        </Link>
        {hasExtraction ? (
          <Link
            href={`/inbox/${id}/review`}
            className={buttonVariants({ variant: "default", size: "sm" })}
          >
            <FileSearch className="mr-1 h-4 w-4" />
            Review extraction
          </Link>
        ) : null}
      </div>
      <div className="grid flex-1 grid-cols-1 gap-4 overflow-hidden lg:grid-cols-[1.5fr_1fr]">
        <PdfViewer documentId={document.id} />
        <DocumentMetaPanel document={document} />
      </div>
    </div>
  );
}
