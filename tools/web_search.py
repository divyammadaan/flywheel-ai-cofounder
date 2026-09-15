"""Free web search to ground Market Research in real, current sources.

Uses DuckDuckGo through the `ddgs` package: no API key, no account, nothing
to pay. One query took ~16s from the dev machine, so the queries run in
parallel. Fails soft: if search is unavailable the agent gets no results and
labels its figures as estimates, rather than the run failing.
"""

from concurrent.futures import ThreadPoolExecutor

MAX_RESULTS_PER_QUERY = 5
MAX_SOURCES = 8
SNIPPET_CHARS = 280


def search(query: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict]:
    try:
        from ddgs import DDGS

        return DDGS().text(query, max_results=max_results) or []
    except Exception:  # noqa: BLE001 - search helps but must never fail a run
        return []


def business_queries(business) -> list[str]:
    region = business.target_region if business.target_region and business.target_region != "unspecified" else "India"
    return [
        f"{business.product_or_service} {region} competitors",
        f"{business.industry} market size {region}",
    ]


def search_business(business) -> list[dict]:
    """Deduplicated sources for a business, as title/url/snippet."""
    queries = business_queries(business)
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        batches = list(pool.map(search, queries))

    sources, seen = [], set()
    for batch in batches:
        for result in batch:
            url = result.get("href")
            if not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                {
                    "title": (result.get("title") or "").strip(),
                    "url": url,
                    "snippet": (result.get("body") or "").strip()[:SNIPPET_CHARS],
                }
            )
    return sources[:MAX_SOURCES]


def describe_sources(sources: list[dict]) -> str:
    if not sources:
        return "No web search results were available: treat every figure as an estimate and say so."
    return "Web search results (cite as [n] where you use one):\n" + "\n".join(
        f"[{i}] {s['title']} -- {s['snippet']} ({s['url']})" for i, s in enumerate(sources, 1)
    )
