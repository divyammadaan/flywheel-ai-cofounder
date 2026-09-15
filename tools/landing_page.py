"""A deployable one-page launch site, built from the plan.

Strategy's positioning, price and target customer, plus Marketing's ad copy
and image, become one self-contained HTML file (the image is embedded; no
external assets). It can be dropped onto any static host as-is: Netlify Drop,
GitHub Pages, or a hosting provider's file manager.

The waitlist form deliberately has no working endpoint. Collecting sign-ups
needs the founder's own account with a form service (Google Forms, Formspree,
Tally), so the page carries a clear note instead of silently losing sign-ups.
"""

import base64
import html
from pathlib import Path

from agents._money import fmt_money

SITE_DIR = Path(__file__).resolve().parent.parent / "data" / "site"

_CSS = """
  :root { --ink:#1d1b18; --muted:#6b645c; --paper:#faf7f2; --accent:#7a4a1e; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,'Segoe UI',sans-serif; color:var(--ink); background:var(--paper); line-height:1.55; }
  main { max-width:760px; margin:0 auto; padding:48px 20px 64px; }
  h1 { font-size:clamp(1.8rem,5vw,2.6rem); line-height:1.15; margin:0 0 16px; }
  .price { font-size:1.3rem; font-weight:600; color:var(--accent); margin:0 0 24px; }
  .price span { font-weight:400; color:var(--muted); font-size:1rem; }
  img { width:100%; border-radius:12px; margin:8px 0 24px; display:block; }
  .copy { font-size:1.1rem; margin:0 0 28px; }
  h2 { font-size:1.1rem; margin:32px 0 8px; }
  form { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
  input { flex:1 1 220px; padding:12px 14px; border:1px solid #d8d0c4; border-radius:8px; font-size:1rem; }
  button { padding:12px 22px; border:0; border-radius:8px; background:var(--accent); color:#fff; font-size:1rem; cursor:pointer; }
  .note { color:var(--muted); font-size:.85rem; margin-top:10px; }
"""


def _embedded_image(image_path: str | None, alt: str) -> str:
    if not image_path or not Path(image_path).exists():
        return ""
    data = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    return f'<img src="data:image/jpeg;base64,{data}" alt="{html.escape(alt)}">'


def build_landing_page(business: dict, strategy: dict, marketing: dict | None = None) -> str:
    """HTML for the launch page, from Decision Record dicts (intake, strategy, marketing)."""
    currency = strategy.get("currency") or business.get("currency", "INR")
    product = business.get("product_or_service") or "Coming soon"
    marketing = marketing or {}

    def esc(value) -> str:
        return html.escape(str(value or ""))

    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{esc(product)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n<main>\n"
        f"<h1>{esc(strategy.get('positioning'))}</h1>\n"
        f"<p class=\"price\">{esc(fmt_money(strategy.get('price'), currency))} "
        f"<span>{esc(strategy.get('price_unit'))}</span></p>\n"
        f"{_embedded_image(marketing.get('ad_image_path'), product)}\n"
        f"<p class=\"copy\">{esc(marketing.get('ad_copy'))}</p>\n"
        "<h2>Made for</h2>\n"
        f"<p>{esc(strategy.get('target_customer'))}</p>\n"
        "<h2>Join the launch list</h2>\n"
        "<!-- To collect sign-ups, set action= to your form service's endpoint "
        "(Google Forms, Formspree, Tally) and method=\"post\". -->\n"
        "<form action=\"#\" onsubmit=\"return false\">\n"
        "<input type=\"text\" name=\"name\" placeholder=\"Your name\" required>\n"
        "<input type=\"tel\" name=\"phone\" placeholder=\"Phone or email\" required>\n"
        "<button type=\"submit\">Notify me</button>\n</form>\n"
        "<p class=\"note\">Sign-ups aren't saved until this form is connected to a form service.</p>\n"
        "</main>\n</body>\n</html>\n"
    )


def write_landing_page(business: dict, strategy: dict, marketing: dict | None = None, out_dir: Path = SITE_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(build_landing_page(business, strategy, marketing), encoding="utf-8")
    return path
