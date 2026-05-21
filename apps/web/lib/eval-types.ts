export type EvalType = "extraction" | "retrieval" | "voice" | "workflow";

export interface EvalRunListItem {
  id: string;
  eval_type: EvalType;
  test_set_version: string;
  num_samples: number;
  run_duration_seconds: number;
  prompt_version: string | null;
  model: string | null;
  created_at: string;
  exact_match_rate: number;
  f1_macro: number;
}

export interface EvalRunListResponse {
  items: EvalRunListItem[];
  total: number;
}

export interface EvalFieldMetric {
  accuracy: number;
  precision: number;
  recall: number;
  f1: number;
  n: number;
}

export interface EvalRunDetail {
  id: string;
  eval_type: EvalType;
  test_set_version: string;
  num_samples: number;
  run_duration_seconds: number;
  prompt_version: string | null;
  model: string | null;
  notes: string | null;
  run_by: string | null;
  created_at: string;
  metrics: {
    aggregate: {
      num_docs: number;
      total_field_observations: number;
      exact_match_rate: number;
      f1_macro: number;
    };
    per_field: Record<string, EvalFieldMetric>;
    per_document?: Array<{
      document: string;
      classification: string;
      exact_match_rate: number;
      f1_macro: number;
    }>;
    provider?: string;
    git_sha?: string | null;
    started_at?: string;
    finished_at?: string;
  };
}

export interface EvalFieldComparison {
  field: string;
  run_a: EvalFieldMetric | null;
  run_b: EvalFieldMetric | null;
  delta: number;
}

export interface EvalCompareResponse {
  run_a_id: string;
  run_b_id: string;
  fields: EvalFieldComparison[];
  aggregate_delta: number;
}
