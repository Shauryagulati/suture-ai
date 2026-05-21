export type DocumentClassification =
  | "referral"
  | "discharge_summary"
  | "lab"
  | "imaging"
  | "other"
  | "unclassified";

export type DocumentStatus =
  | "uploaded"
  | "classifying"
  | "classified"
  | "extracting"
  | "extracted"
  | "needs_review"
  | "reviewed"
  | "processed"
  | "error";

export type UrgencyLevel = "stat" | "urgent" | "routine" | "unclassified";

export interface DocumentListItem {
  id: string;
  file_name: string;
  file_size: number;
  mime_type: string;
  status: DocumentStatus;
  classification: DocumentClassification;
  classification_confidence: number | null;
  urgency: UrgencyLevel;
  ocr_engine: string | null;
  patient_id: string | null;
  uploaded_by: string | null;
  created_at: string;
  updated_at: string;
}

export type DocumentUploadResult = DocumentListItem;

export interface DocumentDetail extends DocumentListItem {
  extracted_text: string | null;
  notes: string | null;
}

export interface DocumentListResponse {
  items: DocumentListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentListFilters {
  status?: DocumentStatus;
  classification?: DocumentClassification;
  urgency?: UrgencyLevel;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface DocumentPatchBody {
  status?: DocumentStatus;
  notes?: string;
}
