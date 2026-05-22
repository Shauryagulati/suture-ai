export interface LeakageRow {
  patient_id: string;
  patient_name: string;
  score: number;
  days_since_referral: number | null;
  failed_outreach_count: number;
  has_phone: boolean;
  has_email: boolean;
  urgency: string;
  prior_auth_denied: boolean;
  referral_id: string | null;
  discharge_summary_id: string | null;
}

export interface LeakageSummary {
  at_risk_count: number;
  threshold: number;
  rows: LeakageRow[];
}

export interface PayerFrictionRow {
  payer_name: string;
  total_auths: number;
  approved: number;
  denied: number;
  pending: number;
  approval_rate: number;
  avg_turnaround_days: number | null;
  top_denial_reasons: string[];
}

export interface PayerFrictionSummary {
  rows: PayerFrictionRow[];
}

export interface ReferralQualityRow {
  provider_id: string;
  provider_name: string;
  practice_name: string | null;
  referral_volume: number;
  avg_missing_fields: number;
  completeness_pct: number;
  top_missing_fields: string[];
}

export interface ReferralQualitySummary {
  rows: ReferralQualityRow[];
}

export interface RoiReport {
  from_date: string;
  to_date: string;
  documents_processed: number;
  hours_saved: number;
  referrals_at_risk: number;
  projected_revenue_recovered_cents: number;
  prior_auth_approval_rate: number | null;
  avg_days_referral_to_appointment: number | null;
}

export interface DashboardPayload {
  leakage: LeakageSummary;
  payer_friction: PayerFrictionSummary;
  referral_quality: ReferralQualitySummary;
  roi: RoiReport;
}
