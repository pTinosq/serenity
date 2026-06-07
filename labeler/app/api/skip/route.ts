import { NextResponse } from "next/server";
import { markSeen } from "@/lib/dataset";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as { tweetId?: string };
    if (!body.tweetId) {
      return NextResponse.json({ error: "tweetId required" }, { status: 400 });
    }
    await markSeen([body.tweetId]);
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
