from pydantic import BaseModel, Field
from uuid import UUID, uuid4
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib

_DATA_DIR = Path(__file__).parent.parent / "project_data"
_OPPORTUNITIES_FILE = _DATA_DIR / "opportunities.json"


class Opportunity(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    designation: str | None = None
    job_description: str | None = None
    location: str | None = None
    company_name: str | None = None
    source_url: str | None = None
    relevant: bool | None = None
    date_posted: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_hash: str | None = None

    def __eq__(self, other):
        if isinstance(other, Opportunity):
            return self.source_hash == other.source_hash
        return False


def load_opportunities() -> list[Opportunity]:
    if not _OPPORTUNITIES_FILE.exists():
        return []
    try:
        with open(_OPPORTUNITIES_FILE) as f:
            return [Opportunity(**v) for v in json.load(f).values()]
    except Exception as e:
        print(f"Error loading opportunities: {e}")
        return []


def save_opportunities(opportunities: "Opportunity | list[Opportunity]") -> bool:
    if isinstance(opportunities, Opportunity):
        opportunities = [opportunities]

    opportunities = [
        opp.model_copy(update={"source_hash": hashlib.sha256(opp.source_url.encode()).hexdigest()})
        for opp in opportunities
    ]

    existing = load_opportunities()
    existing_hashes = {opp.source_hash for opp in existing}
    for opp in opportunities:
        if opp.source_hash not in existing_hashes:
            existing.append(opp)
            existing_hashes.add(opp.source_hash)

    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(_OPPORTUNITIES_FILE, "w") as f:
            json.dump({opp.source_hash: opp.model_dump() for opp in existing}, f, indent=4, default=str)
        return True
    except Exception as e:
        print(f"Error saving opportunities: {e}")
        return False