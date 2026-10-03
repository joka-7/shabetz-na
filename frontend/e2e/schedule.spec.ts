import { expect, test, type Locator } from "@playwright/test";
import { PASSWORD, seedOrganisation } from "./seed";

const EMAIL = "admin@example.com";

/** The person's name in a table row (the cell also holds their avatar initials). */
const personOf = (row: Locator) => row.locator("td").nth(4).locator("span.font-medium");

test.describe("editing a generated schedule", () => {
  test.beforeAll(async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    await seedOrganisation(request, EMAIL);
    await request.dispose();
  });

  test("a manager generates a schedule, changes a shift, and undoes it", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("textbox", { name: "Email" }).fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await page.getByRole("button", { name: "Generate schedule" }).click();
    await expect(page.getByText("Shifts assigned")).toBeVisible();

    // Change who works the first shift listed.
    const firstRow = page.locator("section tbody tr").first();
    const original = (await personOf(firstRow).innerText()).trim();
    await firstRow.getByRole("button", { name: /^Change / }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("Change who works this shift")).toBeVisible();
    await dialog.getByRole("button", { name: /shifts$/ }).first().click();
    await expect(dialog.getByText("No rule is broken by this change.")).toBeVisible();
    await dialog.getByRole("button", { name: "Save change" }).click();

    await expect(page.getByText("Change saved")).toBeVisible();
    await expect(page.locator("section tbody").getByText("edited").first()).toBeVisible();
    await expect(personOf(firstRow)).not.toHaveText(original);

    // The change survives a reload: the schedule lives on the server.
    await page.reload();
    await expect(page.locator("section tbody").getByText("edited").first()).toBeVisible();

    // And it can be taken back.
    // The history sits beside the schedule, so there is nothing to open first.
    await page.getByRole("button", { name: "Undo" }).first().click();
    await expect(page.getByText("Change undone")).toBeVisible();
    await expect(personOf(page.locator("section tbody tr").first())).toHaveText(original);
  });

  test("a change that breaks a rule must be acknowledged", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("textbox", { name: "Email" }).fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await page.getByRole("button", { name: "Generate schedule" }).click();
    await expect(page.getByText("Shifts assigned")).toBeVisible();

    // Whoever works the day window on the first day...
    const start = await page.locator("#start-date").inputValue();
    await page.getByLabel("Search").fill("Day");
    const holder = (await personOf(page.locator("section tbody tr").first()).innerText()).trim();

    // ...is added to that evening too: back to back, with no rest in between.
    await page.getByRole("button", { name: "Add person to a shift" }).click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Job").selectOption({ label: "Front desk" });
    await dialog.getByLabel("Window").selectOption({ label: "Evening" });
    await dialog.getByLabel("Date").fill(start);
    await dialog.getByLabel("Assign to").selectOption({ label: `${holder} — Alpha` });

    await expect(dialog.getByText("This change breaks some rules")).toBeVisible();
    const save = dialog.getByRole("button", { name: "Save change" });
    await expect(save).toBeDisabled();
    await dialog.getByLabel("Assign anyway", { exact: false }).check();
    await expect(save).toBeEnabled();
    await save.click();

    await expect(page.getByText("Change saved")).toBeVisible();
    // The accepted conflict stays visible on the schedule.
    await expect(page.getByText(/required rest|overlapping shift/).first()).toBeVisible();
  });
});
