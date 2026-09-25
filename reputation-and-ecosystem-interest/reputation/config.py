from dataclasses import dataclass, field
from pathlib import Path
import os
import shutil

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=ROOT / '.env.local'):
    """Read server configuration without running shell code or overriding env."""
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                name, value = line.split('=', 1)
                if name.strip() in {'GEMINI_API_KEY', 'GEMINI_MODEL', 'MONID_BIN',
                                    'REPUTATION_DB', 'REPUTATION_ACCESS_TOKEN'}:
                    os.environ.setdefault(name.strip(), value.strip().strip('"\''))


@dataclass
class Settings:
    api_key: str = field(default='', repr=False)
    model: str = 'gemini-3.5-flash-lite'
    monid_bin: str = 'monid'
    db_path: Path = ROOT / '.runtime' / 'reputation.sqlite3'
    access_token: str = field(default='', repr=False)
    max_searches: int = 14
    max_pages: int = 24
    max_model_calls: int = 9
    max_model_attempts: int = 5
    model_timeout_seconds: int = 45
    max_seconds: int = 600
    page_cache_seconds: int = 21600

    @classmethod
    def from_env(cls):
        load_env()
        return cls(api_key=os.environ.get('GEMINI_API_KEY', ''),
                   model=os.environ.get('GEMINI_MODEL', 'gemini-3.5-flash-lite'),
                   monid_bin=os.environ.get('MONID_BIN', 'monid'),
                   db_path=Path(os.environ.get('REPUTATION_DB', str(cls.db_path))),
                   access_token=os.environ.get('REPUTATION_ACCESS_TOKEN', ''))

    def public_status(self):
        return {'model': self.model, 'gemini_configured': bool(self.api_key),
                'search_configured': bool(shutil.which(self.monid_bin)),
                'access_token_required': bool(self.access_token),
                'module': 'Reputation & Ecosystem Interest',
                'billing_note': 'Gemini project quota and billing are managed in Google AI Studio. No billing changes are made by this app.'}
