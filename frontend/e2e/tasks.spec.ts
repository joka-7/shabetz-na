import { expect, test } from "@playwright/test";
import { EMAIL, signIn } from "./helpers";
import { seedOrganisation } from "./seed";

test.describe("tasks, hours and notes", () => {
  test.beforeAll(async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    await seedOrganisation(request, EMAIL);
    await request.dispose();
  });

  test("add a night task with notes, see it, then remove it", async ({ page }) => {
    page.on("dialog", (dialog) => void dialog.accept());
    await signIn(page);
    await page.getByRole("button", { name: "Tasks" }).first().click();
    await expect(page.getByRole("heading", { name: "Front desk" })).toBeVisible();

    await page.getByRole("button", { name: "Add a task" }).click();
    await page.getByLabel("Task name").fill("Night gate");
    await page.getByLabel("People needed").fill("2");
    await page.getByLabel("From").fill("22:00");
    await page.getByLabel("To").fill("06:00");
    await page.getByLabel("Notes").fill("Bring the radio");
    await page.getByRole("button", { name: "Save task" }).click();

    const card = page.getByRole("listitem").filter({ hasText: "Night gate" });
    await expect(card).toContainText("2 people");
    await expect(card).toContainText("22:00–06:00");
    await expect(card).toContainText("Bring the radio");

    // It is saved, not just shown.
    await page.reload();
    await page.getByRole("button", { name: "Tasks" }).first().click();
    await expect(page.getByRole("listitem").filter({ hasText: "Night gate" })).toContainText("Bring the radio");

    // Tidy up so the other tests see the organisation they expect.
    await page.getByRole("button", { name: "Remove Night gate" }).click();
    await expect(page.getByRole("heading", { name: "Night gate" })).toHaveCount(0);
  });
});
