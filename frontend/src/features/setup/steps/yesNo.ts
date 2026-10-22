import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { keys, useLevels } from "@/api/queries";
import { useI18n } from "@/i18n";
import type { BulkResult, ProficiencyLevel } from "@/types/api";

/**
 * Skills are plain yes/no unless levels are chosen on purpose. Underneath,
 * "has the skill" is the one level of a ladder with a single rung, so nothing
 * about how people and jobs are stored changes; with that single rung the
 * pickers for it are simply not shown.
 */
export function useSkillMode() {
  const { data: levels } = useLevels();
  return { levels: levels ?? [], simple: (levels?.length ?? 0) <= 1 };
}

/** Makes sure a ladder exists, adding the single "Yes" rung when it is empty. */
export function useEnsureYesNo() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  return useCallback(async () => {
    const current = await api.get<ProficiencyLevel[]>("/api/config/proficiency-levels");
    if (current.length) return;
    await api.post<BulkResult>("/api/config/proficiency-levels/bulk", {
      names: [t("ladder.yesName")],
    });
    await queryClient.invalidateQueries({ queryKey: keys.levels });
  }, [t, queryClient]);
}
