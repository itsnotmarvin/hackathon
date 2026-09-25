import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv(Path(__file__).resolve().parent / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL:
    raise ValueError("SUPABASE_URL is missing")

if not SUPABASE_SERVICE_ROLE_KEY:
    raise ValueError("SUPABASE_SERVICE_ROLE_KEY is missing")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY
)


def record_evidence(
    entity_type: str,
    entity_id: str,
    claim: str,
    source_name: str | None = None,
    source_url: str | None = None,
    source_date: str | None = None,
    confidence: float | None = None,
) -> dict:
    """Insert one row into `evidence` backing a claim shown in the UI.

    Every fact pulled from an external API should get one of these so the
    frontend can show "why" next to a signal instead of a bare score.
    """
    row = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "claim": claim,
        "source_name": source_name,
        "source_url": source_url,
        "source_date": source_date,
        "confidence": confidence,
    }

    response = supabase.table("evidence").insert(row).execute()
    return response.data[0]