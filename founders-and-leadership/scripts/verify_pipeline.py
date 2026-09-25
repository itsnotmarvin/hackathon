"""Proof-of-life for the founder evidence pipeline.

Runs the real FastAPI app against the real Supabase project and shows,
line by line, that external APIs get called and their results actually
land in the database — not just that the code imports cleanly.

Uses a real person from the team's shared startups.csv (Stephen Socolof /
SunRay Scientific, row L09) so this is meaningful data for the project,
not a throwaway test fixture.

Usage (from founders-and-leadership/):
    .venv/Scripts/python scripts/verify_pipeline.py            # reuse existing data if present
    .venv/Scripts/python scripts/verify_pipeline.py --refresh  # force a fresh pull from every API

Safe to re-run: it reuses the existing startup/founder row by name instead
of creating duplicates every time.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.main  # noqa: E402
from app.database import SUPABASE_URL, supabase  # noqa: E402

DEMO_STARTUP = {
    "name": "SunRay Scientific",
    "city": "Newark",
    "state": "NJ",
    "description": "Verification record - see startups.csv row L09",
}
DEMO_FOUNDER_NAME = "Stephen Socolof"

KNOWN_SOURCES = [
    "OpenCorporates",
    "Wikidata",
    "Semantic Scholar",
    "GitHub",
    "USAspending.gov",
    "NSF Award Search",
    "NIH RePORTER",
]


def get_or_create_startup() -> dict:
    existing = supabase.table("startups").select("*").eq("name", DEMO_STARTUP["name"]).execute().data
    if existing:
        return existing[0]
    return supabase.table("startups").insert(DEMO_STARTUP).execute().data[0]


def get_or_create_founder(startup_id: str) -> dict:
    existing = (
        supabase.table("founders")
        .select("*")
        .eq("startup_id", startup_id)
        .eq("name", DEMO_FOUNDER_NAME)
        .execute()
        .data
    )
    if existing:
        return existing[0]
    return supabase.table("founders").insert({"startup_id": startup_id, "name": DEMO_FOUNDER_NAME}).execute().data[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-run /research even if data already exists")
    args = parser.parse_args()

    client = TestClient(app.main.app)

    startup = get_or_create_startup()
    founder = get_or_create_founder(startup["id"])
    print(f"Startup: {startup['name']}  ({startup['id']})")
    print(f"Founder: {founder['name']}  ({founder['id']})")

    existing = (
        supabase.table("companies").select("id").eq("founder_id", founder["id"]).execute().data
        + supabase.table("achievements").select("id").eq("founder_id", founder["id"]).execute().data
        + supabase.table("grants").select("id").eq("founder_id", founder["id"]).execute().data
    )

    research_warnings = None
    if existing and not args.refresh:
        print(f"\nFounder already has {len(existing)} research rows stored; skipping re-pull (pass --refresh to force).\n")
    else:
        print("\nCalling POST /founders/{id}/research against every live source...\n")
        response = client.post(f"/founders/{founder['id']}/research")
        response.raise_for_status()
        research = response.json()
        research_warnings = research["warnings"]
        print(f"  companies found this run:    {len(research['companies'])}")
        print(f"  achievements found this run: {len(research['achievements'])}")
        print(f"  grants found this run:       {len(research['grants'])}")

    print("\nCalling GET /founders/{id}/profile -- reads back from Supabase fresh, no cache...\n")
    profile = client.get(f"/founders/{founder['id']}/profile").json()

    print("=" * 64)
    print("WHAT'S ACTUALLY STORED IN SUPABASE RIGHT NOW")
    print("=" * 64)
    print(f"  education rows:   {len(profile['education'])}")
    print(f"  company rows:     {len(profile['companies'])}")
    print(f"  achievement rows: {len(profile['achievements'])}")
    print(f"  grant rows:       {len(profile['grants'])}")
    print(f"  evidence rows:    {len(profile['evidence'])}  <- one per sourced fact, this is the proof trail")
    print(f"  signals:          {profile['signals']}")

    if profile["evidence"]:
        print("\nSample evidence rows (claim -> source), pulled straight from the `evidence` table:")
        for e in profile["evidence"][:6]:
            print(f"  - \"{e['claim']}\"  [{e['source_name']}]")

    print("\nPer-API status this run:")
    if research_warnings is not None:
        failed = {w.split(":")[0] for w in research_warnings}
        for src in KNOWN_SOURCES:
            status = "FAILED" if src in failed else "OK"
            print(f"  [{status:^6}] {src}")
        if research_warnings:
            print("\nWarnings (full detail):")
            for w in research_warnings:
                print(f"  - {w}")
    else:
        print("  (skipped this run -- reused existing rows; pass --refresh to re-check every API live)")

    if SUPABASE_URL:
        project_ref = SUPABASE_URL.split("//")[1].split(".")[0]
        print("\nSee it yourself in the Supabase Table Editor:")
        print(f"  https://supabase.com/dashboard/project/{project_ref}/editor")
        print(f"  -> founders table, id = {founder['id']}")
        print("  -> evidence table, filter entity_id to any id printed above")


if __name__ == "__main__":
    main()
