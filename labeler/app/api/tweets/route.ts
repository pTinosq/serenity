import { NextResponse } from "next/server";
import { fetchRecentTweets } from "@/lib/x";
import { readSeenSync } from "@/lib/dataset";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const tweets = await fetchRecentTweets(100);
    const seen = readSeenSync();
    const fresh = tweets.filter((t) => !seen.has(t.id));
    return NextResponse.json({ tweets: fresh, total: tweets.length, seen: seen.size });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
