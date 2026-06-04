export type TaskStatus = "pending" | "in_progress" | "completed" | "cancelled" | "overdue";

export type TaskPriority = "critical" | "high" | "medium" | "low";

export type TaskType =
  | "call_patient"
  | "request_missing_info"
  | "verify_eligibility"
  | "submit_prior_auth"
  | "schedule_appointment"
  | "send_confirmation"
  | "follow_up"
  | "other";

export interface Task {
  id: string;
  clinic_id: string;
  patient_id: string;
  referral_id: string | null;
  discharge_summary_id: string | null;
  task_type: TaskType;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: TaskPriority;
  assigned_to: string | null;
  completed_by: string | null;
  due_at: string | null;
  completed_at: string | null;
  sla_hours: number | null;
  created_at: string;
  updated_at: string;
  patient_first_name: string | null;
  patient_last_name: string | null;
}

export interface TaskListResponse {
  items: Task[];
  total: number;
  limit: number;
  offset: number;
}
