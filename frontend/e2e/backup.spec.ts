import { expect, test } from "@playwright/test";
import { PASSWORD, seedOrganisation } from "./seed";

const EMAIL = "admin@example.com";

test.describe("backup and restore", () => {
  test.beforeAll(async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    await seedOrganisation(request, EMAIL);
    await request.dispose();
  });

  test("a project is saved to a file and the same file loads back as already the same", async ({
    page,
  }) => {
    await page.goto("/");
    await page.getByRole("textbox", { name: "Email" }).fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();

    await page.getByRole("button", { name: "Configuration" }).first().click();
    await page.getByRole("button", { name: "Backup", exact: true }).click();

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByRole("button", { name: "Download backup file" }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(/^shabetz-.*\.json$/);
    const path = await download.path();

    await page.locator('input[type="file"]').setInputFiles(path);
    await expect(page.getByText("This is what loading the file would do:")).toBeVisible();
    // Nothing differs from what is already there, so there is nothing to load.
    await expect(page.getByRole("button", { name: "Nothing to change" })).toBeDisabled();
    await expect(page.getByRole("row", { name: /People/ })).toContainText("4");
  });

  test("a file that is not a backup is refused", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("textbox", { name: "Email" }).fill(EMAIL);
    await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("button", { name: "Configuration" }).first().click();
    await page.getByRole("button", { name: "Backup", exact: true }).click();

    await page.locator('input[type="file"]').setInputFiles({
      name: "nope.json",
      mimeType: "application/json",
      buffer: Buffer.from('{"hello":"world"}'),
    });
    await expect(page.getByText("This is not a Shabetz backup file.")).toBeVisible();
  });
});
