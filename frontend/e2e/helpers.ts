import type { Page } from "@playwright/test";
import { PASSWORD } from "./seed";

export const EMAIL = "admin@example.com";

export async function signIn(page: Page) {
  await page.goto("/");
  await page.getByRole("textbox", { name: "Email" }).fill(EMAIL);
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}
