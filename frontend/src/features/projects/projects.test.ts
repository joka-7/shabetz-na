import { describe, expect, it } from "vitest";
import { can } from "@/hooks/useSession";
import type { Project, ProjectRole } from "@/types/api";
import { inviteTokenFromPath } from "./InvitePage";

const project = (role: ProjectRole): Project => ({ id: 1, name: "P", role, person_id: null });

describe("what each role may do", () => {
  it("mirrors the server: collaborators edit, only administrators manage members", () => {
    expect(can.editConfig(project("ADMIN"))).toBe(true);
    expect(can.editConfig(project("COLLABORATOR"))).toBe(true);
    expect(can.editConfig(project("STAFF"))).toBe(false);

    expect(can.manageMembers(project("ADMIN"))).toBe(true);
    expect(can.manageMembers(project("COLLABORATOR"))).toBe(false);

    expect(can.reviewTimeOff(project("COLLABORATOR"))).toBe(true);
    expect(can.generate(project("STAFF"))).toBe(false);
  });

  it("allows nothing outside a project", () => {
    expect(can.editConfig(null)).toBe(false);
    expect(can.manageMembers(null)).toBe(false);
  });
});

describe("invite links", () => {
  it("reads the token from the path", () => {
    const token = "abcDEF123_-abcDEF123_-abcDEF123_-abcDEF1";
    expect(inviteTokenFromPath(`/invite/${token}`)).toBe(token);
    expect(inviteTokenFromPath(`/invite/${token}/`)).toBe(token);
  });

  it("ignores anything else", () => {
    expect(inviteTokenFromPath("/")).toBeNull();
    expect(inviteTokenFromPath("/invite/")).toBeNull();
    expect(inviteTokenFromPath("/invite/short")).toBeNull();
    expect(inviteTokenFromPath("/invite/has spaces in it here")).toBeNull();
  });
});
