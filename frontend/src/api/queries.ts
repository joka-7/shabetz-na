/** Shared query keys and fetchers. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, request } from "./client";
import type {
  Division,
  Feasibility,
  Invite,
  Job,
  Member,
  Person,
  ProficiencyLevel,
  ScheduleConflict,
  ScheduleRun,
  SlotRef,
  Settings,
  ShiftTemplate,
  Suggestion,
  Skill,
  TimeOff,
} from "@/types/api";

export const keys = {
  divisions: ["divisions"] as const,
  levels: ["proficiency-levels"] as const,
  skills: ["skills"] as const,
  templates: ["shift-templates"] as const,
  jobs: ["jobs"] as const,
  people: ["people"] as const,
  settings: ["settings"] as const,
  feasibility: ["feasibility"] as const,
  timeOff: ["time-off"] as const,
  members: ["members"] as const,
  invites: ["invites"] as const,
};

export const useDivisions = () =>
  useQuery({ queryKey: keys.divisions, queryFn: () => api.get<Division[]>("/api/config/divisions") });

export const useLevels = () =>
  useQuery({
    queryKey: keys.levels,
    queryFn: () => api.get<ProficiencyLevel[]>("/api/config/proficiency-levels"),
  });

export const useSkills = () =>
  useQuery({ queryKey: keys.skills, queryFn: () => api.get<Skill[]>("/api/config/skills") });

export const useTemplates = () =>
  useQuery({
    queryKey: keys.templates,
    queryFn: () => api.get<ShiftTemplate[]>("/api/config/shift-templates"),
  });

export const useJobs = () =>
  useQuery({ queryKey: keys.jobs, queryFn: () => api.get<Job[]>("/api/config/jobs") });

export const usePeople = () =>
  useQuery({ queryKey: keys.people, queryFn: () => api.get<Person[]>("/api/config/people") });

export const useSettings = () =>
  useQuery({ queryKey: keys.settings, queryFn: () => api.get<Settings>("/api/config/settings") });

export const useFeasibility = () =>
  useQuery({
    queryKey: keys.feasibility,
    queryFn: () => api.get<Feasibility>("/api/config/feasibility"),
  });

export const useMembers = () =>
  useQuery({ queryKey: keys.members, queryFn: () => api.get<Member[]>("/api/project/members") });

export const useInvites = () =>
  useQuery({ queryKey: keys.invites, queryFn: () => api.get<Invite[]>("/api/project/invites") });

export const useTimeOff = () =>
  useQuery({ queryKey: keys.timeOff, queryFn: () => api.get<TimeOff[]>("/api/time-off") });

/**
 * Configuration edits change what a schedule can achieve, so anything that
 * writes config also invalidates the feasibility verdict.
 */
export function useConfigMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  invalidate: readonly (readonly string[])[],
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of [...invalidate, keys.feasibility]) {
        void queryClient.invalidateQueries({ queryKey: key });
      }
    },
  });
}

export const generateSchedule = (start_date: string, end_date: string) =>
  api.post<ScheduleRun>("/api/schedule/generate", { start_date, end_date });

// ----------------------------------------------------------- schedule editing

export const runKeys = {
  latest: ["schedule-run", "latest"] as const,
  one: (id: string) => ["schedule-run", id] as const,
};

/**
 * The most recent run, so a reload (or a colleague's edit) shows the current
 * schedule instead of an empty page. Only editors may list runs.
 */
export function useLatestRun(enabled: boolean) {
  return useQuery({
    queryKey: runKeys.latest,
    enabled,
    queryFn: async () => {
      const [latest] = await api.get<{ schedule_id: string }[]>("/api/schedule/runs?limit=1");
      return latest ? api.get<ScheduleRun>(`/api/schedule/runs/${latest.schedule_id}`) : null;
    },
  });
}

const assignmentsUrl = (scheduleId: string) =>
  `/api/schedule/runs/${encodeURIComponent(scheduleId)}/assignments`;

export const checkAssignment = (
  scheduleId: string,
  body: SlotRef & { person_id: number; replaces_person_id?: number | null },
) =>
  api.post<{ conflicts: ScheduleConflict[] }>(`${assignmentsUrl(scheduleId)}/check`, body);

export const fetchSuggestions = (
  scheduleId: string,
  slot: SlotRef,
  replacesPersonId: number | null,
) =>
  api.get<Suggestion[]>(
    `/api/schedule/runs/${encodeURIComponent(scheduleId)}/suggestions?${new URLSearchParams({
      job_id: String(slot.job_id),
      template_id: String(slot.template_id),
      calendar_date: slot.calendar_date,
      ...(replacesPersonId !== null ? { replaces_person_id: String(replacesPersonId) } : {}),
    })}`,
  );

export const reassignShift = (
  scheduleId: string,
  body: SlotRef & {
    from_person_id: number;
    to_person_id: number;
    acknowledge_conflicts: boolean;
  },
) => api.put<ScheduleRun>(assignmentsUrl(scheduleId), body);

export const addShiftPerson = (
  scheduleId: string,
  body: SlotRef & { person_id: number; acknowledge_conflicts: boolean },
) => api.post<ScheduleRun>(assignmentsUrl(scheduleId), body);

export const removeShiftPerson = (scheduleId: string, slot: SlotRef, personId: number) =>
  request<ScheduleRun>(
    `${assignmentsUrl(scheduleId)}?${new URLSearchParams({
      job_id: String(slot.job_id),
      template_id: String(slot.template_id),
      calendar_date: slot.calendar_date,
      person_id: String(personId),
    })}`,
    { method: "DELETE" },
  );
