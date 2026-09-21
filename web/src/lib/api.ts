/**
 * The API client.
 *
 * Errors are unwrapped into a message a founder can act on. FastAPI reports a
 * failed field as a 422 with a `loc`/`msg` list; showing that raw ("body ->
 * starting_capital: Input should be greater than 0") is a stack trace with
 * better grammar, so it is turned back into a sentence.
 */

import type {
  DecisionRecord,
  OrdersPreview,
  Plan,
  RefinableAgent,
  Run,
  RunDetail,
  RunEvent,
  SegmentMeta,
  Usage,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function readableDetail(detail: unknown): { message: string; fields: Record<string, string> } {
  if (typeof detail === "string") return { message: detail, fields: {} };

  if (Array.isArray(detail)) {
    const fields: Record<string, string> = {};
    for (const issue of detail as ValidationIssue[]) {
      // Drop the "body" prefix: the founder filled in a form, not a body.
      const path = (issue.loc ?? []).filter((p) => p !== "body").join(".");
      const msg = (issue.msg ?? "is not valid").replace(/^Value error,\s*/, "");
      if (path) fields[path] = msg;
    }
    const first = Object.entries(fields)[0];
    return {
      message: first ? `${prettyField(first[0])} ${first[1].toLowerCase()}` : "Please check the form.",
      fields,
    };
  }

  return { message: "Something went wrong.", fields: {} };
}

function prettyField(path: string): string {
  const leaf = path.split(".").pop() ?? path;
  const words = leaf.replace(/_/g, " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
    });
  } catch {
    // A dead server is the single most likely failure in development, and
    // "Failed to fetch" tells the founder nothing about what to do.
    throw new ApiError(
      `Can't reach Flywheel at ${API_BASE}. Is the API running?`,
      0,
    );
  }

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = (await response.json())?.detail;
    } catch {
      /* a non-JSON error body is handled by the fallback below */
    }
    const { message, fields } = readableDetail(detail);
    throw new ApiError(message, response.status, fields);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),

  segmentMeta: () => request<SegmentMeta>("/meta/segments"),

  listRuns: (limit = 50) => request<Run[]>(`/runs?limit=${limit}`),

  getRun: (id: number) => request<RunDetail>(`/runs/${id}`),

  getEvents: (id: number, afterSeq = 0) =>
    request<RunEvent[]>(`/runs/${id}/events?after_seq=${afterSeq}`),

  getUsage: (id: number, settle = false) =>
    request<Usage>(`/runs/${id}/usage${settle ? "?settle=true" : ""}`),

  startNewIdea: (body: {
    pitch: string;
    currency: string;
    starting_capital: number;
    monthly_fixed_costs?: number | null;
    unit_cost?: number | null;
    runway_months?: number;
    include_formation?: boolean;
    include_funding?: boolean;
  }) =>
    request<{ run_id: number; status: string }>("/runs/new-idea", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  submitAnswers: (id: number, answers: Record<string, string>) =>
    request<{ run_id: number; status: string }>(`/runs/${id}/answers`, {
      method: "POST",
      body: JSON.stringify({ answers }),
    }),

  startBusinessReview: (body: Record<string, unknown>) =>
    request<{ run_id: number; status: string }>("/runs/existing-business", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  refine: (runId: number, agent: RefinableAgent, cycle: number, feedback: string) =>
    request<DecisionRecord>(`/runs/${runId}/refine`, {
      method: "POST",
      body: JSON.stringify({ agent, cycle, feedback }),
    }),

  previewOrders: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<OrdersPreview>("/orders/preview", { method: "POST", body: form });
  },

  landingPageUrl: (id: number) => `${API_BASE}/runs/${id}/landing-page`,
  sampleOrdersUrl: (extension: "csv" | "xlsx") => `${API_BASE}/orders/sample.${extension}`,
};

/**
 * Gather a run's Decision Records into one object keyed by agent.
 *
 * The latest cycle wins, so a multi-period business shows its newest plan;
 * `cycle` lets a caller pin an earlier one.
 */
export function toPlan(detail: RunDetail, cycle?: number): Plan {
  const byAgent = new Map<string, unknown>();
  const strategyRejections: { problems: string[] }[] = [];
  const fundingRejections: { problems: string[] }[] = [];

  const planCycles = detail.records.map((r) => r.cycle).filter((c) => c > 0);
  const target = cycle ?? (planCycles.length ? Math.max(...planCycles) : 0);

  for (const record of detail.records) {
    if (record.agent === "strategy_rejected") {
      strategyRejections.push({
        problems: (record.input_snapshot.problems as string[]) ?? [],
      });
      continue;
    }
    if (record.agent === "funding_rejected") {
      fundingRejections.push({
        problems: (record.input_snapshot.problems as string[]) ?? [],
      });
      continue;
    }
    // Cycle 0 holds intake, research, the verdict and formation -- they belong
    // to the whole run, not to a period, so they are always kept.
    if (record.cycle === 0 || record.cycle === target) {
      byAgent.set(record.agent, record.decision);
    }
  }

  const get = <T>(agent: string) => byAgent.get(agent) as T | undefined;

  return {
    run: detail.run,
    cycle: target,
    intake: get("intake"),
    research: get("market_research"),
    advisor: get("founder_advisor"),
    formation: get("company_formation"),
    analytics: get("analytics"),
    strategy: get("strategy"),
    finance: get("finance"),
    marketing: get("marketing"),
    sales: get("sales"),
    product: get("product"),
    crm: get("crm"),
    funding: get("funding"),
    strategyRejections,
    fundingRejections,
  };
}

/** Whether an agent's current output in this run is a redone version --
 * i.e. more than one record exists for it in this cycle. Drives the small
 * "Revised on your feedback" note next to its "Suggest a change" control. */
export function wasRevised(detail: RunDetail, agent: string, cycle: number): boolean {
  return detail.records.filter((r) => r.agent === agent && r.cycle === cycle).length > 1;
}

/** Every planned period in a run, oldest first. */
export function planCycles(detail: RunDetail): number[] {
  return [...new Set(detail.records.map((r) => r.cycle).filter((c) => c > 0))].sort(
    (a, b) => a - b,
  );
}
