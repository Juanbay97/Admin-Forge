import type { ApiClient } from "./client";

export interface Department {
  id: string;
  name: string;
}

export interface Organization {
  id: string;
  display_name: string;
  status: "active";
  roles: string[];
  departments: Department[];
}

export interface Me {
  account: { id: string; email: string; display_name: string };
  organizations: Organization[];
}

export interface AccountApi {
  login(email: string, password: string): Promise<string>;
  logout(): Promise<void>;
  me(): Promise<Me>;
  /** Public: spends a one-time capability (a set-password link) to set the password. */
  consumeReset(capability: string, password: string): Promise<void>;
  departments(orgId: string): Promise<Department[]>;
  createDepartment(orgId: string, name: string): Promise<Department>;
}

export function createAccountApi(client: ApiClient): AccountApi {
  return {
    async login(email, password) {
      const session = await client.request<{ access_token: string }>("POST", "/forge/v1/accounts/login", { email, password });
      return session.access_token;
    },
    async logout() {
      await client.request("POST", "/forge/v1/accounts/logout");
    },
    me: () => client.request<Me>("GET", "/forge/v1/accounts/me"),
    async consumeReset(capability, password) {
      await client.request("POST", "/forge/v1/accounts/password-reset/consume", { capability, password });
    },
    createDepartment: (orgId, name) => client.request<Department>("POST", `/forge/v1/orgs/${encodeURIComponent(orgId)}/departments`, { name }),
    async departments(orgId) {
      const body = await client.request<{ departments: Department[] }>(
        "GET",
        `/forge/v1/orgs/${encodeURIComponent(orgId)}/departments`,
      );
      return body.departments;
    },
  };
}