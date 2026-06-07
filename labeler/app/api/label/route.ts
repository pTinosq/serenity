import { NextResponse } from "next/server";
import { appendDatasetCase, markSeen, type DatasetCase } from "@/lib/dataset";

export const dynamic = "force-dynamic";

type LabelBody = {
  tweetId: string;
  case: DatasetCase;
};

function validate(body: unknown): body is LabelBody {
  if (typeof body !== "object" || body === null) return false;
  const b = body as Record<string, unknown>;
  if (typeof b.tweetId !== "string" || !b.tweetId) return false;
  const c = b.case as Record<string, unknown> | undefined;
  if (!c || typeof c.tweet !== "string") return false;
  const r = c.result as Record<string, unknown> | undefined;
  if (!r) return false;
  if (typeof r.ticker !== "string") return false;
  if (!["BUY", "SELL", "N/A"].includes(r.order_type as string)) return false;
  if (typeof r.confidence !== "object" || r.confidence === null) return false;
  return true;
}

export async function POST(req: Request) {
  try {
    const body = await req.json();
    if (!validate(body)) {
      return NextResponse.json({ error: "invalid payload" }, { status: 400 });
    }
    const total = await appendDatasetCase(body.case);
    await markSeen([body.tweetId]);
    return NextResponse.json({ total });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
