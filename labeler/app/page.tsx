"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Tweet = { id: string; text: string; created_at: string };
type OrderType = "BUY" | "SELL" | "N/A";
type ConfidenceOp = "gte" | "lte" | "eq" | "gt" | "lt";

type FetchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; tweets: Tweet[]; total: number; seen: number };

const ORDER_OPTIONS: OrderType[] = ["BUY", "SELL", "N/A"];
const OP_OPTIONS: ConfidenceOp[] = ["gte", "lte", "gt", "lt", "eq"];

function makeEmptyForm() {
  return {
    ticker: "",
    order_type: "BUY" as OrderType,
    confidenceOp: "gte" as ConfidenceOp,
    confidenceValue: 0.7,
  };
}

export default function Page() {
  const [state, setState] = useState<FetchState>({ kind: "idle" });
  const [cursor, setCursor] = useState(0);
  const [form, setForm] = useState(makeEmptyForm);
  const [savedCount, setSavedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const loadTweets = useCallback(async () => {
    setState({ kind: "loading" });
    setCursor(0);
    try {
      const res = await fetch("/api/tweets");
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "failed to fetch tweets");
      setState({
        kind: "ready",
        tweets: json.tweets as Tweet[],
        total: json.total as number,
        seen: json.seen as number,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setState({ kind: "error", message });
    }
  }, []);

  useEffect(() => {
    loadTweets();
  }, [loadTweets]);

  const current = useMemo(() => {
    if (state.kind !== "ready") return null;
    return state.tweets[cursor] ?? null;
  }, [state, cursor]);

  useEffect(() => {
    if (form.order_type === "N/A") {
      setForm((f) => ({ ...f, ticker: "N/A", confidenceOp: "eq", confidenceValue: 0 }));
    }
  }, [form.order_type]);

  function advance() {
    setCursor((c) => c + 1);
    setForm(makeEmptyForm());
    setError(null);
  }

  async function onSkip() {
    if (!current) return;
    setError(null);
    try {
      const res = await fetch("/api/skip", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ tweetId: current.id }),
      });
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json.error ?? "skip failed");
      }
      advance();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onSave() {
    if (!current) return;
    setError(null);
    const ticker = form.ticker.trim().toUpperCase();
    if (!ticker) {
      setError("ticker required (use N/A if no clear ticker)");
      return;
    }
    if (form.order_type !== "N/A" && ticker === "N/A") {
      setError("N/A ticker requires order_type N/A");
      return;
    }
    if (form.order_type === "N/A" && form.confidenceValue !== 0) {
      setError("N/A order must have confidence 0");
      return;
    }
    const payload = {
      tweetId: current.id,
      case: {
        tweet: current.text,
        result: {
          ticker,
          order_type: form.order_type,
          confidence: { [form.confidenceOp]: form.confidenceValue },
        },
      },
    };
    try {
      const res = await fetch("/api/label", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "save failed");
      setSavedCount(json.total as number);
      advance();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <header className="mb-8 flex items-baseline justify-between">
        <h1 className="text-xl font-semibold tracking-tight">Serenity Labeler</h1>
        <div className="text-sm text-neutral-400">
          {savedCount > 0 && <span>dataset: {savedCount} cases · </span>}
          <button
            onClick={loadTweets}
            className="underline decoration-dotted underline-offset-4 hover:text-neutral-200"
          >
            refetch
          </button>
        </div>
      </header>

      {state.kind === "loading" && <p className="text-neutral-400">Fetching tweets…</p>}
      {state.kind === "error" && (
        <div className="rounded border border-red-900 bg-red-950/40 p-4 text-sm text-red-300">
          {state.message}
        </div>
      )}
      {state.kind === "ready" && !current && (
        <div className="rounded border border-neutral-800 bg-neutral-900 p-6 text-sm text-neutral-400">
          No unlabeled tweets. {state.seen} already labeled out of {state.total} fetched.
          Click refetch later for new ones.
        </div>
      )}

      {current && state.kind === "ready" && (
        <>
          <div className="mb-4 text-xs text-neutral-500">
            tweet {cursor + 1} of {state.tweets.length} unlabeled ·{" "}
            {new Date(current.created_at).toLocaleString()}
          </div>

          <article className="mb-6 whitespace-pre-wrap rounded border border-neutral-800 bg-neutral-900 p-5 text-[15px] leading-relaxed">
            {current.text}
          </article>

          <div className="space-y-4 rounded border border-neutral-800 bg-neutral-950 p-5">
            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-neutral-500">
                Ticker
              </label>
              <input
                type="text"
                value={form.ticker}
                onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value }))}
                placeholder="AAPL"
                className="w-full rounded border border-neutral-800 bg-neutral-900 px-3 py-2 font-mono uppercase outline-none focus:border-neutral-600"
              />
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-neutral-500">
                Order type
              </label>
              <div className="flex gap-2">
                {ORDER_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, order_type: opt }))}
                    className={`rounded border px-3 py-1.5 text-sm transition ${
                      form.order_type === opt
                        ? "border-neutral-200 bg-neutral-200 text-neutral-900"
                        : "border-neutral-800 bg-neutral-900 text-neutral-400 hover:border-neutral-600"
                    }`}
                  >
                    {opt}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase tracking-wider text-neutral-500">
                Confidence
              </label>
              <div className="flex items-center gap-2">
                <select
                  value={form.confidenceOp}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, confidenceOp: e.target.value as ConfidenceOp }))
                  }
                  disabled={form.order_type === "N/A"}
                  className="rounded border border-neutral-800 bg-neutral-900 px-2 py-2 font-mono text-sm disabled:opacity-40"
                >
                  {OP_OPTIONS.map((op) => (
                    <option key={op} value={op}>
                      {op}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={form.confidenceValue}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, confidenceValue: Number(e.target.value) }))
                  }
                  disabled={form.order_type === "N/A"}
                  className="w-24 rounded border border-neutral-800 bg-neutral-900 px-3 py-2 font-mono outline-none focus:border-neutral-600 disabled:opacity-40"
                />
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={form.confidenceValue}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, confidenceValue: Number(e.target.value) }))
                  }
                  disabled={form.order_type === "N/A"}
                  className="flex-1 disabled:opacity-40"
                />
              </div>
            </div>

            {error && (
              <div className="rounded border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
                {error}
              </div>
            )}

            <div className="flex gap-2 pt-2">
              <button
                onClick={onSave}
                className="flex-1 rounded bg-emerald-500 px-4 py-2 font-medium text-neutral-950 hover:bg-emerald-400"
              >
                Save
              </button>
              <button
                onClick={onSkip}
                className="rounded border border-neutral-700 bg-neutral-900 px-4 py-2 text-neutral-300 hover:border-neutral-500"
              >
                Skip
              </button>
            </div>
          </div>
        </>
      )}
    </main>
  );
}
