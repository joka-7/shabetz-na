import type { APIRequestContext } from "@playwright/test";

export const PASSWORD = "an-adequately-long-password";
const ALL_DAYS = [0, 1, 2, 3, 4, 5, 6];

/**
 * A small organisation created through the API, so each test starts from the
 * same data without clicking through the setup wizard. Returns the ids the
 * tests need.
 */
export async function seedOrganisation(request: APIRequestContext, email: string) {
  const boot = await request.post("/api/setup/bootstrap-admin", {
    data: { email, full_name: "Dana Admin", password: PASSWORD },
  });
  // Already seeded: a retried worker runs this again against the same database.
  if (boot.status() === 409) return;
  if (!boot.ok()) throw new Error(`bootstrap failed: ${boot.status()} ${await boot.text()}`);
  const { csrf_token: csrf } = await boot.json();

  const projects = await (await request.get("/api/projects")).json();
  const project = String(projects[0].id);
  const headers = { "x-csrf-token": csrf, "x-project-id": project };
  const post = async <T>(url: string, data: unknown): Promise<T> => {
    const response = await request.post(url, { data, headers });
    if (!response.ok()) throw new Error(`${url}: ${response.status()} ${await response.text()}`);
    return response.json();
  };

  const division = await post<{ id: number }>("/api/config/divisions", { name: "Alpha" });
  const day = await post<{ id: number }>("/api/config/shift-templates", {
    name: "Day",
    start_hour: 8,
    duration_hours: 8,
  });
  const evening = await post<{ id: number }>("/api/config/shift-templates", {
    name: "Evening",
    start_hour: 16,
    duration_hours: 8,
  });
  for (const name of ["Ana Levi", "Ben Cohen", "Cat Mizrahi", "Dov Katz"]) {
    await post("/api/config/people", {
      full_name: name,
      division_id: division.id,
      working_weekdays: ALL_DAYS,
    });
  }
  await post("/api/config/jobs", {
    name: "Front desk",
    required_people_per_shift: 1,
    shift_template_ids: [day.id, evening.id],
    requirements: [],
  });
  // Skip the first-run wizard.
  await post("/api/setup/complete", {});
  return { project };
}
