import { readFileSync } from "node:fs";
import { resolve } from "node:path";

type Env = { bearerToken: string; handle: string };

let cached: Env | null = null;

function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    out[key] = value;
  }
  return out;
}

function handleFromUrl(url: string): string {
  const trimmed = url.replace(/\/+$/, "");
  const segment = trimmed.split("/").pop();
  if (!segment) throw new Error(`Cannot parse handle from ${url}`);
  return segment.replace(/^@/, "");
}

export function loadEnv(): Env {
  if (cached) return cached;
  const path = resolve(process.cwd(), "..", ".env");
  const text = readFileSync(path, "utf8");
  const parsed = parseDotenv(text);
  const token = parsed.X_BEARER_TOKEN;
  const url = parsed.TRACKED_X_ACCOUNT;
  if (!token) throw new Error("X_BEARER_TOKEN missing in ../.env");
  if (!url) throw new Error("TRACKED_X_ACCOUNT missing in ../.env");
  cached = { bearerToken: token, handle: handleFromUrl(url) };
  return cached;
}
