/** Tiny typed wrapper around the FastAPI backend. */

const API_URL = "http://localhost:8000";

export type Me = {
  id: number;
  github_id: number;
  login: string;
  avatar_url: string | null;
};

export type Repo = {
  id: number | null;
  name: string | null;
  full_name: string | null;
  private: boolean;
  description: string | null;
  language: string | null;
  stargazers_count: number | null;
  default_branch: string | null;
  html_url: string | null;
  installation_id: number;
  account_login: string;
};

export type ReposResponse = {
  repositories: Repo[];
  errors: {
    installation_id: number;
    account_login: string;
    error: string;
  }[];
  installations: {
    id: number;
    installation_id: number;
    account_login: string;
  }[];
};

/** FastAPI error bodies are `{ detail: string }`. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    // The session lives in a cookie on :8000, so it must be sent.
    credentials: "include",
    ...init,
  });

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // Non-JSON error body; keep the status line.
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function getMe(): Promise<Me> {
  return request<Me>("/auth/me");
}

export function getRepos(): Promise<ReposResponse> {
  return request<ReposResponse>("/repos");
}

export function logout(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/auth/logout", { method: "POST" });
}

/** Full-page redirect into the backend's OAuth flow. */
export function signInWithGitHub(): void {
  window.location.href = `${API_URL}/auth/github/login`;
}
export function installApp(): void {
  window.location.href = `${API_URL}/auth/github/install`;
}

export { API_URL };
