"""Health check for every external API this project touches - including
ones that aren't wired into /research (PDL, USPTO TSDR) and ones known to
be dead (SBIR.gov). Doesn't touch Supabase or any founder record; it's a
pure "is each API reachable right now" check, independent of the pipeline.

Usage (from founders-and-leadership/):
    .venv/Scripts/python scripts/check_all_apis.py

Each row is one of:
  OK        - got a real, successful response, live, just now
  NO KEY    - correctly skipped because its required env var isn't set
              (this is not a failure - see .env.example)
  FAIL      - the call was attempted and failed; see the message
  DEAD      - known non-functional, not attempted (see the service's
              module docstring for why)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / "app" / ".env")

from services import college_scorecard  # noqa: E402
from services import gdelt  # noqa: E402
from services import github  # noqa: E402
from services import grants  # noqa: E402
from services import nih  # noqa: E402
from services import nsf  # noqa: E402
from services import orcid  # noqa: E402
from services import pdl  # noqa: E402
from services import scholar  # noqa: E402
from services import sec  # noqa: E402
from services import uspto  # noqa: E402
from services import wikidata  # noqa: E402
from services import wikipedia  # noqa: E402

results: list[tuple[str, str, str]] = []  # (name, status, detail)


def check(name: str, fn):
    start = time.monotonic()
    try:
        out = fn()
        elapsed = time.monotonic() - start
        results.append((name, "OK", f"{elapsed:.2f}s - {str(out)[:80]}"))
    except Exception as exc:  # noqa: BLE001 - this script's whole job is to catch and report these
        elapsed = time.monotonic() - start
        results.append((name, "FAIL", f"{elapsed:.2f}s - {type(exc).__name__}: {exc}"))


def check_requires_key(name: str, env_var: str, fn):
    if not os.getenv(env_var):
        results.append((name, "NO KEY", f"{env_var} not set in app/.env"))
        return
    check(name, fn)


def check_dead(name: str, reason: str):
    results.append((name, "DEAD", reason))


print("Checking every API this project uses, live, right now...\n")

# --- Keyless, always attempted ---
check("Wikidata", lambda: wikidata.search_person("Elon Musk")[:1])
check("Wikipedia", lambda: wikipedia.get_summary("Elon Musk")["title"])
check("Semantic Scholar", lambda: scholar.search_author("Geoffrey Hinton")[:1])
check("ORCID", lambda: orcid.search_person("Geoffrey", "Hinton")[:1])
check("GDELT", lambda: gdelt.search_articles('"Elon Musk"', max_records=1))
check("GitHub", lambda: github.get_user("torvalds")["login"])
check("SEC EDGAR", lambda: sec.search_filings("Tesla", forms="D")[:1])
check("USAspending.gov", lambda: grants.search_federal_awards("Lockheed Martin")[:1])
check("NSF Award Search", lambda: nsf.search_awards_by_pi("Fei-Fei", "Li")[:1])
check("NIH RePORTER", lambda: nih.search_projects_by_pi("Anthony", "Fauci")[:1])
check("College Scorecard", lambda: college_scorecard.lookup_school("Rutgers")["school.name"])

# --- Require a key - report NO KEY cleanly instead of attempting ---
check_requires_key("People Data Labs (PDL)", "PDL_API_KEY", lambda: pdl.enrich_person("Elon Musk"))
check_requires_key(
    "USPTO TSDR",
    "USPTO_API_KEY",
    lambda: uspto.get_trademark_status("73033741", is_registration=False),
)

# --- Known dead, not attempted (see module docstrings for the evidence) ---
check_dead("OpenCorporates", "removed - paid-only API, 401s on every request without a token")
check_dead("SBIR.gov awards", "403 Forbidden on every request as of 2026-09-25, not wired into /research")
check_dead("arXiv", "406 on every requests call from this stack despite a real API (works via curl only)")
check_dead("PatentsView / USPTO Assignment API", "hostnames used previously do not resolve")

print(f"{'API':<32} {'STATUS':<8} DETAIL")
print("-" * 100)
for name, status, detail in results:
    print(f"{name:<32} {status:<8} {detail}")

ok = sum(1 for _, s, _ in results if s == "OK")
no_key = sum(1 for _, s, _ in results if s == "NO KEY")
fail = sum(1 for _, s, _ in results if s == "FAIL")
dead = sum(1 for _, s, _ in results if s == "DEAD")
print(f"\n{ok} OK, {no_key} missing a key, {fail} failed, {dead} known-dead (not attempted)")
