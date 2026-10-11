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
  departments(orgId: string): Promise<Department[]>;
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
    async departments(orgId) {
      const body = await client.request<{ departments: Department[] }>(
        "GET",
        `/forge/v1/orgs/${encodeURIComponent(orgId)}/departments`,
      );
      return body.departments;
    },
  };
}