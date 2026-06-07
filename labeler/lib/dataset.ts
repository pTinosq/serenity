import { readFile, writeFile, rename, mkdir } from "node:fs/promises";
import { existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";

export type OrderType = "BUY" | "SELL" | "N/A";
export type ConfidenceOp = "gte" | "lte" | "eq" | "gt" | "lt";

export type DatasetCase = {
  tweet: string;
  result: {
    ticker: string;
    order_type: OrderType;
    confidence: Partial<Record<ConfidenceOp, number>>;
  };
};

const DATASET_PATH = resolve(process.cwd(), "..", "evals", "dataset.json");
const SEEN_PATH = resolve(process.cwd(), "data", "seen.json");

async function readJson<T>(path: string, fallback: T): Promise<T> {
  if (!existsSync(path)) return fallback;
  const text = await readFile(path, "utf8");
  return JSON.parse(text) as T;
}

async function writeJsonAtomic(path: string, value: unknown): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const tmp = `${path}.tmp`;
  await writeFile(tmp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  await rename(tmp, path);
}

export async function readDataset(): Promise<DatasetCase[]> {
  return readJson<DatasetCase[]>(DATASET_PATH, []);
}

export async function appendDatasetCase(item: DatasetCase): Promise<number> {
  const current = await readDataset();
  current.push(item);
  await writeJsonAtomic(DATASET_PATH, current);
  return current.length;
}

export function readSeenSync(): Set<string> {
  if (!existsSync(SEEN_PATH)) return new Set();
  return new Set<string>(JSON.parse(readFileSync(SEEN_PATH, "utf8")));
}

export async function markSeen(ids: string[]): Promise<void> {
  const current = readSeenSync();
  for (const id of ids) current.add(id);
  await writeJsonAtomic(SEEN_PATH, [...current]);
}
