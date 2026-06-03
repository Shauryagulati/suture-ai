"use client";

import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

// Self-host the worker — no third-party fetch during PDF rendering (HIPAA hygiene).
// The worker in public/ MUST be byte-identical to the pdfjs version react-pdf
// runs. react-pdf@9.2.1 hard-pins pdfjs-dist@4.8.69, so apps/web pins the same
// EXACT version (see package.json) and ships its 4.8.69 worker here. Do not
// float this to ^4.x or ^5.x without re-syncing public/pdf.worker.min.mjs —
// a version skew silently breaks PDF rendering ("API X vs Worker Y").
pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs";

interface Props {
  documentId: string;
}

export function PdfViewer({ documentId }: Props): React.ReactElement {
  const [numPages, setNumPages] = useState<number>(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [pageWidth, setPageWidth] = useState<number | undefined>(undefined);

  useEffect(() => {
    function updateWidth(): void {
      const container = document.getElementById("pdf-viewer-container");
      if (container) {
        setPageWidth(Math.min(container.clientWidth - 32, 900));
      }
    }
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  return (
    <div className="flex h-full flex-col rounded-md border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={pageNumber <= 1}
            onClick={() => setPageNumber((p) => Math.max(1, p - 1))}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm tabular-nums">
            {pageNumber} / {numPages || "—"}
          </span>
          <Button
            variant="ghost"
            size="sm"
            disabled={pageNumber >= numPages}
            onClick={() => setPageNumber((p) => Math.min(numPages, p + 1))}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="sm" onClick={() => setScale((s) => Math.max(0.5, s - 0.1))}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-sm tabular-nums">{Math.round(scale * 100)}%</span>
          <Button variant="ghost" size="sm" onClick={() => setScale((s) => Math.min(2.0, s + 0.1))}>
            <ZoomIn className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <div
        id="pdf-viewer-container"
        className="flex flex-1 items-start justify-center overflow-auto bg-muted/40 p-4"
      >
        <Document
          file={`/api/documents/${documentId}/file`}
          onLoadSuccess={({ numPages: n }) => {
            setNumPages(n);
            setPageNumber(1);
          }}
          loading={<div className="p-8 text-sm text-muted-foreground">Loading PDF…</div>}
          error={<div className="p-8 text-sm text-destructive">Failed to load PDF.</div>}
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            width={pageWidth}
            renderAnnotationLayer={false}
            renderTextLayer={true}
          />
        </Document>
      </div>
    </div>
  );
}
