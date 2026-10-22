import { expect, test } from "@playwright/test";
import { EMAIL, signIn } from "./helpers";
import { seedOrganisation } from "./seed";

test.describe("attendance and the status report", () => {
  test.beforeAll(async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    await seedOrganisation(request, EMAIL);
    await request.dispose();
  });

  test("mark everyone present, then one person absent with a reason", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Attendance" }).first().click();

    await page.getByRole("button", { name: "Mark everyone present" }).click();
    await expect(page.locator("#share-text")).toHaveValue(/4 people: 4 present, 0 absent/);

    await page.getByRole("button", { name: "Mark Ben Cohen absent" }).click();
    await page.getByLabel("Reason for Ben Cohen").fill("Sick");
    await page.getByLabel("Reason for Ben Cohen").blur();

    const report = page.locator("#share-text");
    await expect(report).toHaveValue(/4 people: 3 present, 1 absent/);
    await expect(report).toHaveValue(/Ben Cohen — Sick/);

    // The mark is on the server, not just on the screen.
    await page.reload();
    await page.getByRole("button", { name: "Attendance" }).first().click();
    await expect(page.getByLabel("Reason for Ben Cohen")).toHaveValue("Sick");

    // Pressing the active button again clears the mark.
    await page.getByRole("button", { name: "Mark Ben Cohen absent" }).click();
    await expect(page.locator("#share-text")).toHaveValue(/Not marked[\s\S]*Ben Cohen/);
  });
});
