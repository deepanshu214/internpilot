// Single-user password auth: a signed cookie, verified in middleware (Web Crypto works on edge and node).
export const COOKIE = "ip_session";

const secret = () => process.env.DASHBOARD_SECRET || process.env.DASHBOARD_PASSWORD || "";

export const authEnabled = () => Boolean(process.env.DASHBOARD_PASSWORD);

export async function sessionToken(): Promise<string> {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret()), { name: "HMAC", hash: "SHA-256" },
    false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode("internpilot-session-v1"));
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, "0")).join("");
}

export function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
