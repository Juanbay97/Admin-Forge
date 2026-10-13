import type { Member } from "../api/members";
import type { MemberUsage } from "../api/usage";
import { tokensOf } from "../platform/usage";

export interface Person extends MemberUsage {
  department: string | null;
}

export interface Summary {
  people: number;
  active: number;
  withUsage: number;
  requests: number;
  tokens: number;
  cost_micros: number;
  unpriced: number;
}

export function summarize(people: readonly Person[]): Summary {
  return people.reduce<Summary>(
    (sum, person) => ({
      people: sum.people + 1,
      active: sum.active + (person.state === "active" ? 1 : 0),
      withUsage: sum.withUsage + (person.requests > 0 ? 1 : 0),
      requests: sum.requests + person.requests,
      tokens: sum.tokens + tokensOf(person),
      cost_micros: sum.cost_micros + person.cost_micros,
      unpriced: sum.unpriced + person.unpriced_requests,
    }),
    { people: 0, active: 0, withUsage: 0, requests: 0, tokens: 0, cost_micros: 0, unpriced: 0 },
  );
}

export const shareOf = (person: MemberUsage, totalTokens: number): number => (totalTokens > 0 ? tokensOf(person) / totalTokens : 0);

export function topPeople(people: readonly Person[], count: number, by: "tokens" | "cost"): Person[] {
  const measure = (person: Person) => (by === "tokens" ? tokensOf(person) : person.cost_micros);
  return people.filter((person) => measure(person) > 0).sort((a, b) => measure(b) - measure(a)).slice(0, count);
}

/** The usage report has no department; it comes from the member list, matched by email. */
export function withDepartments(usage: readonly MemberUsage[], members: readonly Member[]): Person[] {
  const byEmail = new Map(members.map((member) => [member.email.toLowerCase(), member.departments.map((department) => department.name).join(", ") || null]));
  return usage.map((row) => ({ ...row, department: byEmail.get(row.email.toLowerCase()) ?? null }));
}

export function filterPeople(people: readonly Person[], { q, department }: { q: string; department: string }): Person[] {
  const needle = q.trim().toLowerCase();
  return people.filter(
    (person) => (!department || (person.department ?? "").split(", ").includes(department)) && (!needle || `${person.name} ${person.email}`.toLowerCase().includes(needle)),
  );
}