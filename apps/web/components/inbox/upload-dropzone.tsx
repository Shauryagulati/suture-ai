"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { DocumentUploadResult } from "@/lib/document-types";
import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type DragEvent, useRef, useState } from "react";
import { toast } from "sonner";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface UploadState {
  status: "idle" | "uploading" | "success" | "error";
  progress: number;
  message?: string;
}

function postWithProgress(
  file: File,
  onProgress: (pct: number) => void,
): Promise<{ status: number; body: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.responseText });
    xhr.onerror = () => reject(new Error("network error"));
    const fd = new FormData();
    fd.set("file", file);
    xhr.send(fd);
  });
}

export function UploadDropzone({ open, onOpenChange }: Props): React.ReactElement {
  const [state, setState] = useState<UploadState>({ status: "idle", progress: 0 });
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const queryClient = useQueryClient();
  const router = useRouter();

  async function handleFile(file: File): Promise<void> {
    if (file.type !== "application/pdf") {
      toast.error("Only PDF files are accepted.");
      return;
    }
    setState({ status: "uploading", progress: 0 });
    try {
      const { status, body } = await postWithProgress(file, (pct) =>
        setState((s) => ({ ...s, progress: pct })),
      );
      if (status >= 200 && status < 300) {
        const data = JSON.parse(body) as Pick<
          DocumentUploadResult,
          "classification" | "classification_confidence"
        > & { id: string };
        const conf =
          data.classification_confidence != null
            ? ` · ${Math.round(data.classification_confidence * 100)}%`
            : "";
        toast.success(`Classified as ${data.classification}${conf}`);
        setState({ status: "success", progress: 100 });
        await queryClient.invalidateQueries({ queryKey: ["documents"] });
        router.refresh();
        onOpenChange(false);
        setState({ status: "idle", progress: 0 });
      } else {
        let detail = `upload failed (${status})`;
        try {
          const parsed = JSON.parse(body) as { detail?: string };
          if (parsed.detail) detail = parsed.detail;
        } catch {
          // body wasn't JSON
        }
        toast.error(detail);
        setState({ status: "error", progress: 0, message: detail });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "upload failed";
      toast.error(msg);
      setState({ status: "error", progress: 0, message: msg });
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>): void {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  }

  function onChange(e: ChangeEvent<HTMLInputElement>): void {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload document</DialogTitle>
          <DialogDescription>
            Drop a referral or discharge PDF. We&apos;ll OCR and classify it automatically.
          </DialogDescription>
        </DialogHeader>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
            dragOver ? "border-primary bg-accent" : "border-muted-foreground/30"
          }`}
        >
          {state.status === "uploading" ? (
            <>
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <p className="text-sm">Uploading… {state.progress}%</p>
              <p className="text-xs text-muted-foreground">
                Classification can take a few seconds after the upload finishes.
              </p>
            </>
          ) : (
            <>
              <FileUp className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm">
                Drag a PDF here, or{" "}
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="font-medium text-primary underline-offset-4 hover:underline"
                >
                  browse
                </button>
                .
              </p>
              <p className="text-xs text-muted-foreground">PDF only. Max 25 MB.</p>
              <input
                ref={fileInputRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={onChange}
              />
            </>
          )}
        </div>

        {state.status === "error" ? (
          <p className="text-sm text-destructive">{state.message}</p>
        ) : null}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
