import { expect, test } from "@playwright/test";
import { EMAIL, signIn } from "./helpers";
import { seedOrganisation } from "./seed";

test.describe("the schedule by shift, and sharing it", () => {
  test.beforeAll(async ({ playwright, baseURL }) => {
    const request = await playwright.request.newContext({ baseURL });
    await seedOrganisation(request, EMAIL);
    await request.dispose();
  });

  test("a generated schedule can be read by shift and shared as text", async ({ page }) => {
    await signIn(page);
    await page.getByRole("button", { name: "Generate schedule" }).click();
    await expect(page.getByText("Shifts assigned")).toBeVisible();

    await page.getByRole("button", { name: "By shift" }).click();
    // Each shift window with the task worked in it.
    await expect(page.getByRole("heading", { name: /Day/ })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Evening/ })).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: "Front desk" }).first()).toBeVisible();

    await page.getByRole("button", { name: "Share" }).click();
    const text = page.locator("#share-text");
    await expect(text).toHaveValue(/Guard roster — /);
    await expect(text).toHaveValue(/Front desk \(1\/1\)/);
    await expect(page.getByRole("link", { name: "Open in WhatsApp" })).toHaveAttribute(
      "href",
      /^https:\/\/wa\.me\/\?text=/,
    );

    // The whole schedule is a longer message.
    const day = (await text.inputValue()).length;
    await page.getByRole("button", { name: "Whole schedule" }).click();
    expect((await text.inputValue()).length).toBeGreaterThan(day);
  });
});
