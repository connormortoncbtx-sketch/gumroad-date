"""
upload.py — Texas Construction Intelligence
Fetches subscriber list from Cloudflare Worker, then sends
each subscriber their weekly download links via Resend.

Required GitHub secrets:
  RESEND_API_KEY       — from resend.com/api-keys
  WORKER_URL           — e.g. https://tx-intel-subs.YOUR_SUBDOMAIN.workers.dev
  WORKER_SECRET        — shared secret set on the Worker
  GITHUB_REPO          — e.g. connormortoncbtx-sketch/gumroad-date
  FROM_EMAIL           — verified sender email in Resend (e.g. intel@yourdomain.com)
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TODAY      = datetime.utcnow().strftime("%Y%m%d")
TODAY_DISP = datetime.utcnow().strftime("%B %d, %Y")
CLEAN_DIR  = Path("data/clean")
GITHUB_API = "https://api.github.com"
RESEND_API = "https://api.resend.com/emails"


def get_env(key):
    val = os.environ.get(key)
    if not val:
        log.error(f"Missing required env var: {key}")
        sys.exit(1)
    return val


def fmt_usd(val):
    try:
        v = float(val)
        if v >= 1_000_000_000: return f"${v/1_000_000_000:.1f}B"
        if v >= 1_000_000:     return f"${v/1_000_000:.1f}M"
        return f"${v:,.0f}"
    except Exception:
        return "—"


def load_summary():
    files = sorted(CLEAN_DIR.glob("summary_*.json"), reverse=True)
    return json.loads(files[0].read_text()) if files else {}


def get_release_urls(repo, tag):
    url = f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=20)
    resp.raise_for_status()
    release = resp.json()
    urls = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    return urls, release.get("html_url", "")


def get_subscribers(worker_url, worker_secret):
    resp = requests.get(
        f"{worker_url}/subs",
        params={"secret": worker_secret},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("subscribers", [])


def send_email(api_key, from_email, to_email, subject, html_body):
    resp = requests.post(
        RESEND_API,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": from_email, "to": to_email, "subject": subject, "html": html_body},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def build_email_html(tier, csv_url, pdf_url, release_url, summary):
    c = summary.get("contracts", {})
    total_val = fmt_usd(c.get("total_value", 0))
    total_cnt = int(c.get("total_count", 0))
    top_counties = list(c.get("by_county", {}).keys())[:3]
    county_str = ", ".join(top_counties) if top_counties else "Texas statewide"

    pdf_row = ""
    if tier == "tier3" and pdf_url:
        pdf_row = f"""
        <tr>
          <td style="padding:12px 0; border-bottom:1px solid #e2e8f0;">
            <strong>📄 PDF Digest</strong><br>
            <a href="{pdf_url}" style="color:#1A7F6E;">{pdf_url}</a>
          </td>
        </tr>"""

    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#1E293B;">
      <div style="background:#0D2137;padding:24px;border-radius:8px 8px 0 0;">
        <h1 style="color:white;margin:0;font-size:20px;">TX Construction Intelligence</h1>
        <p style="color:#B0C4D8;margin:4px 0 0;">Week of {TODAY_DISP}</p>
      </div>

      <div style="background:#F0F4F8;padding:16px;display:flex;gap:16px;">
        <div style="flex:1;background:white;padding:16px;border-radius:6px;text-align:center;">
          <div style="font-size:24px;font-weight:bold;color:#0D2137;">{total_cnt:,}</div>
          <div style="font-size:12px;color:#64748B;">Federal contracts</div>
        </div>
        <div style="flex:1;background:white;padding:16px;border-radius:6px;text-align:center;">
          <div style="font-size:24px;font-weight:bold;color:#0D2137;">{total_val}</div>
          <div style="font-size:12px;color:#64748B;">Total contract value</div>
        </div>
        <div style="flex:1;background:white;padding:16px;border-radius:6px;text-align:center;">
          <div style="font-size:16px;font-weight:bold;color:#0D2137;">{county_str}</div>
          <div style="font-size:12px;color:#64748B;">Top counties</div>
        </div>
      </div>

      <div style="padding:24px;">
        <h2 style="color:#0D2137;font-size:16px;">Your downloads</h2>
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:12px 0; border-bottom:1px solid #e2e8f0;">
              <strong>📊 Weekly Dataset (CSV)</strong><br>
              <a href="{csv_url}" style="color:#1A7F6E;">{csv_url}</a>
            </td>
          </tr>
          {pdf_row}
          <tr>
            <td style="padding:12px 0;">
              <strong>🔗 Full release page</strong><br>
              <a href="{release_url}" style="color:#1A7F6E;">{release_url}</a>
            </td>
          </tr>
        </table>

        <p style="color:#64748B;font-size:12px;margin-top:24px;">
          Data sourced from USASpending.gov. Questions? Reply to this email.<br>
          TX Construction Intelligence · Unsubscribe via Gumroad
        </p>
      </div>
    </div>
    """


def main():
    log.info("=== TX Construction Intel — upload.py ===")

    resend_key    = get_env("RESEND_API_KEY")
    worker_url    = get_env("WORKER_URL")
    worker_secret = get_env("WORKER_SECRET")
    repo          = get_env("GITHUB_REPO")
    from_email    = get_env("FROM_EMAIL")

    # Get release URLs
    tag = f"weekly-{TODAY}"
    log.info(f"Fetching GitHub release: {tag}")
    asset_urls, release_url = get_release_urls(repo, tag)

    csv_url = next((v for k, v in asset_urls.items() if k.endswith(".csv") and "contracts" in k), "")
    pdf_url = next((v for k, v in asset_urls.items() if k.endswith(".pdf")), "")

    if not csv_url:
        log.error("No contracts CSV found in release")
        sys.exit(1)

    # Load summary stats
    summary = load_summary()

    # Get subscribers
    log.info("Fetching subscribers from Worker...")
    subscribers = get_subscribers(worker_url, worker_secret)
    log.info(f"Found {len(subscribers)} subscribers")

    if not subscribers:
        log.info("No subscribers yet — skipping email send")
        return

    # Send emails
    total_val = fmt_usd(summary.get("contracts", {}).get("total_value", 0))
    subject   = f"TX Construction Intel — Week of {TODAY_DISP} ({total_val} in contracts)"
    sent = 0

    for sub in subscribers:
        email = sub.get("email")
        tier  = sub.get("tier", "tier2")
        if not email:
            continue
        try:
            html = build_email_html(tier, csv_url, pdf_url, release_url, summary)
            send_email(resend_key, from_email, email, subject, html)
            log.info(f"  Sent to {email} ({tier})")
            sent += 1
        except Exception as e:
            log.warning(f"  Failed to send to {email}: {e}")

    log.info(f"=== Done — {sent}/{len(subscribers)} emails sent ===")


if __name__ == "__main__":
    main()
