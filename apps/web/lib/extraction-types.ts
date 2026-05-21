import type { DocumentClassification } from "./document-types";

export interface ExtractionListItem {
  id: string;
  document_id: string;
  document_file_name: string;
  classification: DocumentClassification;
  human_review_required: boolean;
  created_at: string;
  avg_confidence: number;
  missing_fields_count: number;
}

export interface ExtractionListResponse {
  items: ExtractionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface HumanEdit {
  field: string;
  old: unknown;
  new: unknown;
  edited_by: string;
  edited_at: string;
}

export interface ExtractionDetail {
  id: string;
  document_id: string;
  document_file_name: string;
  classification: DocumentClassification;
  extraction_data: Record<string, unknown>;
  field_confidences: Record<string, number>;
  missing_fields: string[];
  human_edits: HumanEdit[];
  human_review_required: boolean;
  extraction_version: number;
  created_at: string;
  human_reviewed_by: string | null;
  human_reviewed_at: string | null;
  model: string | null;
  prompt_version: string | null;
  avg_confidence: number;
}

export interface ExtractionPatchBody {
  field_path: string;
  new_value: unknown;
}

export interface ExtractionApproveResponse {
  referral_id: string | null;
  discharge_summary_id: string | null;
  patient_id: string;
  patient_created: boolean;
  referring_provider_id: string | null;
  provider_created: boolean | null;
}
