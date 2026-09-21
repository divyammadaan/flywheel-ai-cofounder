/**
 * Formatting, and one rule about missing values.
 *
 * `null` here almost never means "we failed to load it" -- it means the
 * founder did not report that number. Churn, CAC and cash-in-bank are
 * genuinely optional because many small businesses do not track them. So a
 * missing value is written out as "not reported", never as 0 and never as a
 * blank: a zero churn rate is a claim, and an empty cell looks like a bug.
 */

export const NOT_REPORTED = "not reported";
export const NONE_GIVEN = "—";

const CURRENCY_SYMBOL: Record<string, string> = {
  INR: "₹",
  USD: "$",
  EUR: "€",
  GBP: "£",
};

export function currencySymbol(currency = "INR"): string {
  return CURRENCY_SYMBOL[currency] ?? `${currency} `;
}

/**
 * Mirrors `agents/_money.py:fmt_money` -- symbol before the sign, grouped
 * thousands, no decimals unless the amount genuinely has them.
 *
 * Grouping is "en-US" (1,500,000) and not "en-IN" (15,00,000) deliberately.
 * The backend groups this way, and the same amount appears in both registers
 * on one screen: Finance's explanation is generated in Python, the figures
 * beside it are formatted here. Two spellings of one number reads as a bug.
 * The Indian affordance a founder actually wants -- lakh and crore -- is in
 * moneyCompact below, where it does not collide with anything.
 */
export function money(amount: number | null | undefined, currency = "INR"): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return NONE_GIVEN;
  const symbol = currencySymbol(currency);
  const sign = amount < 0 ? "-" : "";
  const value = Math.abs(amount);
  // Python uses 2dp below 100 and none above; matching keeps ₹899 and ₹12.50
  // rendering identically on both sides.
  const decimals = value >= 100 ? 0 : 2;
  return `${sign}${symbol}${value.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/**
 * Money shortened for a tile, where the full figure would wrap.
 *
 * Indian numbering, because the amounts are Indian: a founder in Bangalore
 * reads "₹9L" faster than "₹900K", and "₹1.5Cr" faster than "₹1,500,000".
 */
export function moneyCompact(amount: number | null | undefined, currency = "INR"): string {
  if (amount === null || amount === undefined || Number.isNaN(amount)) return NONE_GIVEN;
  const symbol = currencySymbol(currency);
  const sign = amount < 0 ? "-" : "";
  const value = Math.abs(amount);

  if (currency === "INR") {
    if (value >= 1e7) return `${sign}${symbol}${trim(value / 1e7)}Cr`;
    if (value >= 1e5) return `${sign}${symbol}${trim(value / 1e5)}L`;
    if (value >= 1e3) return `${sign}${symbol}${trim(value / 1e3)}K`;
  } else {
    if (value >= 1e9) return `${sign}${symbol}${trim(value / 1e9)}B`;
    if (value >= 1e6) return `${sign}${symbol}${trim(value / 1e6)}M`;
    if (value >= 1e3) return `${sign}${symbol}${trim(value / 1e3)}K`;
  }
  return money(amount, currency);
}

function trim(value: number): string {
  return value >= 10 ? Math.round(value).toString() : value.toFixed(1).replace(/\.0$/, "");
}

/**
 * A share, rounded the way Python rounds it.
 *
 * Python's `f"{x:.0%}"` rounds half to even, JavaScript's `toFixed` rounds
 * half away from zero. On this page that difference was visible: the sales
 * budget is exactly 12.5% of the total, so the legend said 13% while
 * Finance's own explanation -- generated in Python from the same number --
 * said 12%, two inches away. Banker's rounding here makes them agree.
 */
export function percent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_REPORTED;
  return `${roundHalfToEven(value * 100, digits).toFixed(digits)}%`;
}

function roundHalfToEven(value: number, digits: number): number {
  const factor = 10 ** digits;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  // Not exactly on a half: ordinary rounding.
  if (Math.abs(diff - 0.5) > Number.EPSILON * Math.max(1, Math.abs(scaled))) {
    return Math.round(scaled) / factor;
  }
  return (floor % 2 === 0 ? floor : floor + 1) / factor;
}

export function count(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NOT_REPORTED;
  // Same grouping as money(), so a quantity and an amount never disagree
  // about where the commas go when they sit in the same table row.
  return value.toLocaleString("en-US");
}

/** "20 Sep 2026" from an ISO date, or the input if it isn't one. */
export function date(value: string | null | undefined): string {
  if (!value) return NONE_GIVEN;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const seconds = Math.round((Date.now() - parsed.getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return date(value);
}

export function tokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return NONE_GIVEN;
  if (value >= 1000) return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return value.toString();
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return NONE_GIVEN;
  if (value >= 60) return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  return `${value.toFixed(1)}s`;
}

/**
 * A list field, whatever shape it arrived in.
 *
 * The agents send arrays. A Decision Record written before the schema change
 * holds the same field as a paragraph, and those runs are still in the
 * database, so a string is kept whole as a single item rather than dropped.
 */
export function asList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((v) => String(v).trim()).filter(Boolean);
  }
  if (typeof value === "string" && value.trim()) return [value.trim()];
  return [];
}

export function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1).replace(/_/g, " ");
}

/** "marketing" -> "Marketing", but "crm" -> "CRM". */
export function agentLabel(agent: string): string {
  const special: Record<string, string> = {
    crm: "CRM",
    market_research: "Market research",
    founder_advisor: "Founder advisor",
    company_formation: "Company formation",
  };
  return special[agent] ?? titleCase(agent);
}
