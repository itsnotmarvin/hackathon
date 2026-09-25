"""Intellectual property signals: trademark status via USPTO TSDR.

Important caveats:

- USPTO does not publish a public "search trademarks/patents by owner name"
  REST API. TSDR (below) only looks up a *known* serial or registration
  number; TESS (the searchable trademark database) has no supported API.

- A prior version of this file called PatentsView at
  "search.patentsview.org" for inventor-name search. That hostname does not
  exist (confirmed via public DNS, not just this network, on 2026-09-25) —
  it was a hallucinated endpoint and has been removed rather than left in
  as dead code. PatentsView's classic API domain (api.patentsview.org) now
  serves USPTO's Open Data Portal web app for every path instead of JSON.
  The real successor looks to live at api.uspto.gov (a probe there returned
  401 Unauthorized, i.e. a real, auth-gated route, not a 403 "no such
  route"), but its request schema is unverified without a registered ODP
  API key — don't wire that back in until it's been confirmed against a
  real key and the current docs.

Docs: https://developer.uspto.gov/tsdr-api
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

TSDR_STATUS_URL = "https://tsdrapi.uspto.gov/ts/cd/casestatus/{kind}{number}/info.json"


def get_trademark_status(serial_or_registration_number: str, is_registration: bool = False) -> dict | None:
    """Look up a *known* trademark's status via TSDR. Requires USPTO_API_KEY.
    `kind` is "rn" for a registration number or "sn" for a serial number."""
    api_key = os.getenv("USPTO_API_KEY")
    if not api_key:
        raise RuntimeError("USPTO_API_KEY is missing")

    kind = "rn" if is_registration else "sn"
    url = TSDR_STATUS_URL.format(kind=kind, number=serial_or_registration_number)

    response = requests.get(url, headers={"USPTO-API-KEY": api_key}, timeout=30)
    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()
