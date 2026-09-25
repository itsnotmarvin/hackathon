"""Wipe the founder-evidence tables and repopulate them with real data from
the team's shared startups.csv (not test fixtures).

Usage (from founders-and-leadership/):
    .venv/Scripts/python scripts/reset_and_seed.py --wipe --seed

    --wipe   delete every row from every table this project owns (asks for
             an explicit "yes" typed at the prompt first - not just the flag)
    --seed   populate real startups/founders/companies from startups.csv,
             then run external-API research once per unique person

Run with just --wipe to clear without reseeding, or just --seed to seed
without wiping first (safe either way - seeding is idempotent, it reuses
existing rows by name instead of duplicating them).

What "seed" actually does, and why it's not a 1:1 CSV import:
  startups.csv has one row per (company, person, relationship) - e.g.
  Stephen Socolof appears 4 times, once per company he's tied to. But this
  schema's `founders` table is one row per PERSON (with one home startup),
  and `companies` is where every company relationship for that person goes.
  So each unique person becomes exactly one founder row (attached to their
  first-listed company), and every row from the CSV becomes a `companies`
  row under that one founder - as ground-truth data straight from the
  team's own research, with the CSV's source_url as evidence, which is
  more authoritative than anything an API guesses. External-API research
  then runs once per person on top of that, not once per CSV row.
"""

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app.main  # noqa: E402
from app.database import record_evidence, supabase  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CSV_PATH = REPO_ROOT / "startups.csv"

# Order matters for readability only - Postgres FK cascades handle real
# dependency order; evidence has no FK so it's included explicitly.
ALL_TABLES = ["evidence", "achievements", "trademarks", "grants", "companies", "education", "founders", "startups"]
NIL_UUID = "00000000-0000-0000-0000-000000000000"


def wipe():
    print("This will permanently delete ALL rows from:")
    for t in ALL_TABLES:
        count = supabase.table(t).select("id", count="exact").limit(1).execute().count
        print(f"  {t}: {count} rows")
    confirm = input("\nType 'yes' to permanently delete all of the above: ").strip().lower()
    if confirm != "yes":
        print("Aborted - nothing deleted.")
        return False

    for t in ALL_TABLES:
        supabase.table(t).delete().neq("id", NIL_UUID).execute()
        print(f"  cleared {t}")
    print("Wipe complete.\n")
    return True


def seed():
    client = TestClient(app.main.app)

    by_person = defaultdict(list)
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_person[row["person"]].append(row)

    total_rows = sum(len(v) for v in by_person.values())
    print(f"startups.csv: {len(by_person)} unique people across {total_rows} company relationships\n")

    for person, rows in by_person.items():
        home = rows[0]

        startup = supabase.table("startups").select("*").eq("name", home["company"]).execute().data
        startup = startup[0] if startup else supabase.table("startups").insert(
            {"name": home["company"], "state": "NJ"}
        ).execute().data[0]

        founder = supabase.table("founders").select("*").eq("startup_id", startup["id"]).eq("name", person).execute().data
        if founder:
            founder = founder[0]
            print(f"{person}: reusing founder {founder['id']} (home: {home['company']})")
        else:
            founder = supabase.table("founders").insert(
                {"startup_id": startup["id"], "name": person, "title": home["relationship"]}
            ).execute().data[0]
            print(f"{person}: created founder {founder['id']} (home: {home['company']})")

        existing = {
            (c["company_name"], c["role"])
            for c in supabase.table("companies").select("company_name,role").eq("founder_id", founder["id"]).execute().data
        }
        for row in rows:
            key = (row["company"], row["relationship"])
            if key in existing:
                continue
            saved = supabase.table("companies").insert(
                {
                    "founder_id": founder["id"],
                    "company_name": row["company"],
                    "role": row["relationship"],
                    "source_name": "Team research (startups.csv)",
                    "source_url": row["source_url"] or None,
                }
            ).execute().data[0]
            record_evidence(
                entity_type="company",
                entity_id=saved["id"],
                claim=f"{person} is a {row['relationship']} at {row['company']}",
                source_name="Team research (startups.csv)",
                source_url=row["source_url"] or row.get("additional_source_url") or None,
            )
            existing.add(key)
            print(f"    + {row['company']} ({row['relationship']})")

        print(f"    calling /founders/{founder['id']}/research ...")
        response = client.post(f"/founders/{founder['id']}/research")
        response.raise_for_status()
        data = response.json()
        print(
            f"    -> +{len(data['achievements'])} achievements, +{len(data['grants'])} grants this call"
            f"  |  warnings: {data['warnings'] or 'none'}"
        )
        print()

    print("Seed complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wipe", action="store_true", help="delete every row first (asks for confirmation)")
    parser.add_argument("--seed", action="store_true", help="populate real data from startups.csv")
    args = parser.parse_args()

    if not args.wipe and not args.seed:
        parser.error("pass --wipe, --seed, or both")

    if args.wipe:
        if not wipe():
            sys.exit(1)

    if args.seed:
        seed()
