import { expect, test } from "@playwright/test";
import { filterPeople, shareOf, summarize, topPeople, withDepartments, type Person } from "../../src/company/people";

const row = (name: string, email: string, tokens: number, cost: number, extra: Partial<Person> = {}): Person => ({
  member_id: name, email, name, state: "active", requests: tokens > 0 ? 1 : 0, prompt_tokens: tokens, completion_tokens: 0, estimated_requests: 0, error_requests: 0, cost_micros: cost, unpriced_requests: 0, department: null, ...extra,
});
const people = [row("Alex", "alex@x.test", 800, 900), row("Pat", "pat@x.test", 150, 100), row("Sam", "sam@x.test", 0, 0, { state: "suspended" }), row("Bea", "bea@x.test", 50, 5)];

test.describe("people usage", () => {
  test("totals and how many people used Forge", () => {
    expect(summarize(people)).toEqual({ people: 4, active: 3, withUsage: 3, requests: 3, tokens: 1000, cost_micros: 1005, unpriced: 0 });
  });
  test("share is each person's part of the tokens, and zero when nobody used anything", () => {
    expect(shareOf(people[0]!, 1000)).toBe(0.8);
    expect(shareOf(people[0]!, 0)).toBe(0);
  });
  test("the top people are ranked by the chosen measure and never include people with nothing", () => {
    expect(topPeople(people, 2, "tokens").map((item) => item.name)).toEqual(["Alex", "Pat"]);
    expect(topPeople(people, 5, "tokens").map((item) => item.name)).toEqual(["Alex", "Pat", "Bea"]);
    expect(topPeople(people, 1, "cost").map((item) => item.name)).toEqual(["Alex"]);
  });
  test("departments come from the member list, matched by email without regard to case", () => {
    const joined = withDepartments([{ ...people[0]!, email: "ALEX@x.test" }, people[1]!], [
      { id: "m1", email: "alex@x.test", display_name: "Alex", status: "active", roles: [], departments: [{ id: "d1", name: "Legal" }] },
    ]);
    expect(joined.map((item) => item.department)).toEqual(["Legal", null]);
  });
  test("search matches name or email and the department filter is exact", () => {
    const joined = people.map((item, index) => ({ ...item, department: index < 2 ? "Legal" : "Finance" }));
    expect(filterPeople(joined, { q: "pat", department: "" }).map((item) => item.name)).toEqual(["Pat"]);
    expect(filterPeople(joined, { q: "", department: "Finance" }).map((item) => item.name)).toEqual(["Sam", "Bea"]);
    expect(filterPeople(joined, { q: "x.test", department: "Legal" })).toHaveLength(2);
  });
});