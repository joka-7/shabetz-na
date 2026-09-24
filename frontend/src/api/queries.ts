/** Shared query keys and fetchers. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  Division,
  Feasibility,
  Invite,
  Job,
  Member,
  Person,
  ProficiencyLevel,
  ScheduleRun,
  Settings,
  ShiftTemplate,
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
