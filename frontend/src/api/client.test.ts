import { describe, expect, it } from "vitest";
import { ApiError, parseBody } from "./client";
import { errorText } from "@/i18n/errors";
import { translate } from "@/i18n";

const t = (key: Parameters<typeof translate>[1]) => translate("en", key);

describe("responses that are not JSON", () => {
  it("parse to nothing instead of throwing", () => {
    expect(parseBody("<html>Bad gateway</html>")).toBeUndefined();
    expect(parseBody("")).toBeUndefined();
    expect(parseBody('{"code":"X","detail":"y"}')).toEqual({ code: "X", detail: "y" });
  });

  it("read as the server starting up when a proxy answered for it", () => {
    const error = new ApiError(502, "UNKNOWN", "Bad Gateway");
    expect(errorText(error, t)).toBe(translate("en", "error.serverUnavailable"));
  });

  it("explain a schedule someone else changed first", () => {
    expect(errorText(new ApiError(409, "STALE", "x"), t)).toBe(translate("en", "error.stale"));
  });
});
