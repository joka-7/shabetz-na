/**
 * API types.
 *
 * Kept in step with the backend by `make types`, which regenerates this file
 * from the live OpenAPI schema; CI fails on a diff.
 */

export type UserRole = "ADMIN" | "SCHEDULER" | "STAFF";
export type DivisionPolicy =
  | "ACTIVE_DIVISION_ONLY"
  | "ACTIVE_DIVISION_PREFERRED"
  | "ANY_DIVISION";
export type TimeOffStatus = "PENDING" | "APPROVED" | "DENIED" | "CANCELLED";
export type FeasibilityVerdict = "OK" | "TIGHT" | "INFEASIBLE";
export type WarningSeverity = "ERROR" | "WARNING" | "INFO";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  person_id: number | null;
}

export interface SessionResponse {
  user: User;
  csrf_token: string;
}

export interface Division {
  id: number;
  name: string;
  display_order: number;
  color: string | null;
  is_active: boolean;
}

export interface ProficiencyLevel {
  id: number;
  name: string;
  rank: number;
  is_active: boolean;
}

export interface Skill {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface ShiftTemplate {
  id: number;
  name: string;
  start_hour: number;
  duration_hours: number;
  color: string | null;
  is_active: boolean;
}

export interface Requirement {
  id: number;
  skill_id: number;
  min_level_id: number;
  required_count: number | null;
  is_leadership: boolean;
  skill_name: string | null;
}

export interface Job {
  id: number;
  name: string;
  required_people_per_shift: number;
  division_policy: DivisionPolicy;
  priority: number | null;
  is_active: boolean;
  shift_template_ids: number[];
  requirements: Requirement[];
}

export interface PersonSkill {
  skill_id: number;
  level_id: number;
}

export interface Person {
  id: number;
  full_name: string;
  division_id: number;
  external_ref: string | null;
  is_active: boolean;
  working_weekdays: number[];
  skills: PersonSkill[];
}

export interface Settings {
  rest_period_hours: number;
  rotation_enabled: boolean;
  rotation_block_days: number;
  rotation_anchor_date: string | null;
  organization_name: string;
  timezone: string;
  week_start: number;
  setup_completed: boolean;
}

export interface SkillFloor {
  skill_id: number;
  skill_name: string;
  min_rank: number;
  needed_distinct: number;
  available: number;
  satisfied: boolean;
}

export interface DivisionFeasibility {
  division_id: number;
  division_name: string;
  headcount: number;
  expected_available: number;
  minimum_distinct_needed: number;
  verdict: FeasibilityVerdict;
  messages: string[];
  skill_floors: SkillFloor[];
}

export interface WindowDemand {
  template_id: number;
  template_name: string;
  start_hour: number;
  duration_hours: number;
  concurrent_people: number;
}

export interface Feasibility {
  verdict: FeasibilityVerdict;
  person_shifts_per_day: number;
  minimum_distinct_needed: number;
  peak_concurrent_people: number;
  window_demand: WindowDemand[];
  divisions: DivisionFeasibility[];
  messages: string[];
}

export interface Assignment {
  person_id: number;
  person_name: string;
  division_id: number;
  job_id: number;
  job_name: string;
  template_id: number;
  template_name: string;
  calendar_date: string;
  start_abs: number;
  end_abs: number;
  role: "ROLE" | "MEMBER";
  is_division_fallback: boolean;
  satisfied_requirement_id: number | null;
}

export interface ScheduleWarning {
  kind: string;
  severity: WarningSeverity;
  message: string;
  calendar_date: string | null;
  job_id: number | null;
  template_id: number | null;
  required: number | null;
  assigned: number | null;
}

export interface ScheduleSummary {
  total_assignments: number;
  total_people: number;
  people_used: number;
  utilization_rate: number;
  understaffed_shift_count: number;
  division_fallback_count: number;
  active_division_by_day: Record<string, number | null>;
  shifts_per_division: Record<string, number>;
}

export interface ScheduleRun {
  schedule_id: string;
  created_at: string | null;
  params: Record<string, unknown>;
  summary: ScheduleSummary;
  assignments: Assignment[];
  warnings: ScheduleWarning[];
}

export interface TimeOff {
  id: number;
  person_id: number;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: TimeOffStatus;
  review_note: string | null;
  created_at: string | null;
}

export interface Capabilities {
  deployment: "server" | "desktop";
  setup_code_required: boolean;
  google_enabled: boolean;
  export_formats: string[];
  pdf_available: boolean;
  setup_complete: boolean;
}

export interface AdminUser extends User {
  has_password: boolean;
  has_google: boolean;
  last_login_at: string | null;
  is_locked: boolean;
}
