import { describe, expect, it } from "vitest";
import { en } from "./en";
import { he } from "./he";
import { translate, translatePlural } from "./index";

const placeholders = (text: string) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();

describe("dictionaries", () => {
  it("have no empty Hebrew strings", () => {
    expect(Object.entries(he).filter(([, text]) => !text.trim())).toEqual([]);
  });

  it("fill in the same values in both languages", () => {
    // A singular may drop {count} ("one person"), so plurals' _one forms are
    // only checked for not inventing values the English lacks.
    const mismatched = (Object.keys(en) as (keyof typeof en)[]).filter((key) => {
      const english = placeholders(en[key]);
      const hebrew = placeholders(he[key]);
      if (key.endsWith("_one")) return hebrew.some((name) => !english.includes(name));
      return english.join() !== hebrew.join();
    });
    expect(mismatched).toEqual([]);
  });
});

describe("translate", () => {
  it("fills placeholders and leaves unknown ones visible", () => {
    expect(translate("en", "common.removeNamed", { name: "North" })).toBe("Remove North");
    expect(translate("en", "common.removeNamed")).toBe("Remove {name}");
  });

  it("picks the singular or plural form", () => {
    expect(translatePlural("en", "people.count", 1)).toBe("1 person");
    expect(translatePlural("en", "people.count", 3)).toBe("3 people");
    expect(translatePlural("he", "people.count", 1)).toBe("אדם אחד");
    expect(translatePlural("he", "people.count", 3)).toBe("3 אנשים");
  });
});
