import { loadEnv } from "./env";

export type Tweet = { id: string; text: string; created_at: string };

type UserLookupResponse = { data?: { id: string }; errors?: unknown };
type TimelineResponse = {
  data?: Array<{
    id: string;
    text: string;
    created_at: string;
    note_tweet?: { text: string };
  }>;
  errors?: unknown;
};

async function xFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`https://api.x.com/2${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`X API ${path} failed: ${res.status} ${body}`);
  }
  return (await res.json()) as T;
}

const userIdCache = new Map<string, string>();

async function resolveUserId(handle: string, token: string): Promise<string> {
  const cached = userIdCache.get(handle);
  if (cached) return cached;
  const json = await xFetch<UserLookupResponse>(
    `/users/by/username/${encodeURIComponent(handle)}`,
    token,
  );
  if (!json.data?.id) throw new Error(`User ${handle} not found`);
  userIdCache.set(handle, json.data.id);
  return json.data.id;
}

export async function fetchRecentTweets(maxResults = 100): Promise<Tweet[]> {
  const { bearerToken, handle } = loadEnv();
  const userId = await resolveUserId(handle, bearerToken);
  const capped = Math.max(5, Math.min(100, maxResults));
  const json = await xFetch<TimelineResponse>(
    `/users/${userId}/tweets?max_results=${capped}&tweet.fields=created_at,note_tweet&exclude=retweets,replies`,
    bearerToken,
  );
  return (json.data ?? []).map((t) => ({
    id: t.id,
    created_at: t.created_at,
    text: t.note_tweet?.text ?? t.text,
  }));
}
