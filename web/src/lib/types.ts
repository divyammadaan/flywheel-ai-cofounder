/**
 * The shapes the agents produce.
 *
 * `api-schema.d.ts` is generated from the live FastAPI schema and covers the
 * request/response envelopes. It cannot cover what is inside a Decision
 * Record's `decision`, because that column is JSON -- so the per-agent shapes
 * are written out here, mirroring the dataclasses in `agents/`.
 *
 * Every field that the Python side made a `list[str]` is a `string[]` here.
 * That is the whole point of the schema change: the UI renders real lists
 * instead of guessing where to split a paragraph.
 */

export type Verdict = "GO" | "PIVOT" | "NO_GO";
export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_answers"
  | "done"
  | "failed"
  | "blocked";

export interface Run {
  id: number;
  workspace_id: number;
  mode: "new_idea" | "existing_business" | null;
  label: string | null;
  status: RunStatus;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface RunEvent {
  seq: number;
  run_id: number;
  kind:
    | "started"
    | "agent_started"
    | "agent_finished"
    | "awaiting_answers"
    | "blocked"
    | "failed"
    | "finished";
  agent: string | null;
  message: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface DecisionRecord<T = Record<string, unknown>> {
  id: number;
  cycle: number;
  agent: string;
  input_snapshot: Record<string, unknown>;
  decision: T;
  timestamp: string;
}

export interface RunDetail {
  run: Run;
  records: DecisionRecord[];
  events: RunEvent[];
}

// ----------------------------------------------------------- the agents --

export interface Intake {
  mode: string;
  business_summary: string;
  industry: string;
  product_or_service: string;
  target_region: string;
  currency: string;
  starting_capital: number;
  offering_type: "physical" | "service" | "software";
  monthly_fixed_costs: number | null;
  unit_cost: number | null;
  runway_months: number;
}

export interface Source {
  title: string;
  url: string;
}

export interface MarketResearch {
  market_size_estimate: string;
  key_competitors: string[];
  opportunities: string[];
  risks: string[];
  clarifying_questions: string[];
  sources: Source[];
}

export interface AdvisorDecision {
  verdict: Verdict;
  rationale: string[];
  seed_positioning: string;
  seed_price: number;
  seed_price_unit: string;
}

export interface FormationPlan {
  recommended_entity: string;
  entity_rationale: string;
  registration_steps: string[];
  licenses_and_permits: string[];
  tax_registrations: string[];
  estimated_cost: string;
  estimated_timeline: string;
  disclaimer: string;
}

export interface Analytics {
  cycle: number;
  currency: string;
  period_label: string;
  metrics: Record<string, number | null>;
  kpis: Record<string, number | null>;
  /** The single most important thing the numbers say. */
  headline?: string;
  points?: string[];
  /** headline + points as one string; kept for records written before the split. */
  summary: string;
  file_metrics: Record<string, unknown> | null;
}

export interface Strategy {
  cycle: number;
  mode: string;
  currency: string;
  positioning: string;
  target_customer: string;
  price: number;
  price_unit: string;
  priorities: Record<string, number>;
  rationale: string[];
}

/**
 * Finance is the one agent that makes no model call: `health` and the split
 * are arithmetic, and `rationale` is written from those numbers in code. The
 * UI marks it as computed for exactly that reason.
 */
export interface FinanceHealth {
  capital?: number;
  monthly_fixed_costs?: number;
  runway_months_reserved?: number;
  reserve?: number;
  launch_budget?: number;
  price?: number;
  contribution_margin?: number;
  break_even_units_per_month?: number | null;
  monthly_net_profit?: number;
  profitable?: boolean;
  runway_months?: number | null;
  debt_to_annual_revenue?: number | null;
  budget_share_of_cash?: number | null;
  warnings?: string[];
}

export interface Finance {
  cycle: number;
  currency: string;
  total_budget: number;
  marketing: number;
  product: number;
  sales: number;
  crm: number;
  rationale: string;
  health: FinanceHealth;
}

export interface Campaign {
  channel: string;
  where: string;
  ad_format: string;
  objective: string;
  duration: string;
  budget: number;
}

export interface Marketing {
  cycle: number;
  budget: number;
  currency: string;
  campaigns: Campaign[];
  ad_copy: string;
  ad_image_path: string | null;
  budget_adjusted: boolean;
}

export interface LeadSource {
  where: string;
  how: string;
  weekly_actions: string;
  budget: number;
}

export interface Sales {
  cycle: number;
  budget: number;
  currency: string;
  lead_sources: LeadSource[];
  conversion_process: string[];
  budget_adjusted: boolean;
}

export interface LineItem {
  item: string;
  units: number;
  unit: string;
  unit_cost: number;
  total_cost: number;
}

export interface Product {
  cycle: number;
  budget: number;
  currency: string;
  plan_type: "inventory" | "capacity";
  line_items: LineItem[];
  line_items_total: number;
  sourcing_plan: string[];
  replenish_policy: string[];
  cost_basis: string;
  budget_adjusted: boolean;
}

export interface SegmentStat {
  label: string;
  customers: number;
  revenue: number;
  revenue_share: number | null;
  avg_orders: number | null;
}

export interface TopSlipping {
  customer: string;
  orders: number;
  spent: number;
  days_since_last_order: number;
}

export interface CrmSegments {
  as_of: string;
  typical_gap_days: number;
  gap_measured: boolean;
  customers: number;
  segments: Record<string, SegmentStat>;
  top_slipping: TopSlipping[];
}

export interface Crm {
  cycle: number;
  budget: number;
  currency: string;
  segments: CrmSegments;
  changes: Record<string, number>;
  actions: Record<string, string>;
  spend: Record<string, number>;
  slipping_message: string;
  lost_message: string;
  message_previews?: { customer: string; message: string }[];
  warnings: string[];
  budget_adjusted: boolean;
}

export interface Funding {
  mode: string;
  currency: string;
  readiness: string;
  readiness_rationale: string[];
  target_raise_date: string;
  target_stage: string;
  revenue_milestone: string;
  profit_milestone: string;
  traction_milestones: string[];
  investor_profile: string;
  alternative_funding: string;
  pitch_deck_outline: string[];
  warnings: string[];
}

export interface UsageAgent {
  agent: string;
  calls: number;
  cache_hits: number;
  prompt_tokens: number;
  completion_tokens: number;
  seconds: number;
}

export interface Usage {
  agents: UsageAgent[];
  totals: Record<string, number>;
}

export interface SegmentMeta {
  order: string[];
  labels: Record<string, string>;
  definitions: Record<string, string>;
}

export interface OrdersPreview {
  token: string;
  rows: number;
  skipped_rows: number;
  customers: number;
  first_order: string | null;
  last_order: string | null;
  columns: string[];
}

/** The plan, with each agent's record pulled out by name. */
export interface Plan {
  run: Run;
  intake?: Intake;
  research?: MarketResearch;
  advisor?: AdvisorDecision;
  formation?: FormationPlan;
  analytics?: Analytics;
  strategy?: Strategy;
  finance?: Finance;
  marketing?: Marketing;
  sales?: Sales;
  product?: Product;
  crm?: Crm;
  funding?: Funding;
  /** Cycles Strategy was sent back, so the UI can say the check caught something. */
  strategyRejections: { problems: string[] }[];
  fundingRejections: { problems: string[] }[];
}
