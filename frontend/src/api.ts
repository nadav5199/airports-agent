import type { Airport, ChatRequest, ChatResponse } from "./types";

// Configurable backend base URL. Set VITE_API_BASE_URL in frontend/.env to
// override; defaults to the local backend dev server per the task spec.
export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

export async function fetchAirports(): Promise<Airport[]> {
  const resp = await fetch(`${API_BASE_URL}/api/airports`);
  if (!resp.ok) {
    throw new Error(`GET /api/airports failed: ${resp.status} ${resp.statusText}`);
  }
  return resp.json() as Promise<Airport[]>;
}

export async function postChat(req: ChatRequest): Promise<ChatResponse> {
  const resp = await fetch(`${API_BASE_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = JSON.stringify(body);
    } catch {
      // ignore, keep statusText
    }
    throw new Error(`POST /api/chat failed: ${resp.status} ${detail}`);
  }
  return resp.json() as Promise<ChatResponse>;
}
