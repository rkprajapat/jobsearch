import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from configs import PROJECT_DATA_DIR

_OPPORTUNITIES_FILE = PROJECT_DATA_DIR.joinpath("opportunities.json")


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
    applied: bool = False
    applied_date: datetime | None = None
    resume_version_used: str | None = None
    cover_letter_version_used: str | None = None

    def __eq__(self, other):
        if isinstance(other, Opportunity):
            return self.source_hash == other.source_hash
        return False


def load_opportunities() -> list[Opportunity]:
    if not _OPPORTUNITIES_FILE.exists():
        return []
    try:
        with open(_OPPORTUNITIES_FILE) as f:
            payload = json.load(f)
            if not isinstance(payload, dict):
                return []
            return [
                Opportunity.model_validate(v)
                for v in payload.values()
                if isinstance(v, dict)
            ]
    except Exception as e:
        print(f"Error loading opportunities: {e}")
        return []


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _merge_opportunity(existing: Opportunity, incoming: Opportunity) -> Opportunity:
    existing_data = existing.model_dump()
    incoming_data = incoming.model_dump()
    user_managed_fields = {
        "relevant",
        "applied",
        "applied_date",
        "resume_version_used",
        "cover_letter_version_used",
    }

    merged_data: dict[str, Any] = {}
    for field_name, existing_value in existing_data.items():
        incoming_value = incoming_data.get(field_name)
        if field_name in user_managed_fields and incoming_value is not None:
            merged_data[field_name] = incoming_value
            continue

        merged_data[field_name] = (
            incoming_value
            if _is_missing_value(existing_value)
            and not _is_missing_value(incoming_value)
            else existing_value
        )

    return Opportunity.model_validate(merged_data)


def save_opportunities(opportunities: "Opportunity | list[Opportunity]") -> bool:
    if isinstance(opportunities, Opportunity):
        opportunities = [opportunities]

    opportunities = [
        opp.model_copy(
            update={"source_hash": hashlib.sha256(opp.source_url.encode()).hexdigest()}
        )
        for opp in opportunities
        if opp.source_url
    ]

    existing_by_hash = {
        opp.source_hash: opp for opp in load_opportunities() if opp.source_hash
    }
    for opp in opportunities:
        source_hash = opp.source_hash
        if not source_hash:
            continue
        existing = existing_by_hash.get(source_hash)
        existing_by_hash[source_hash] = (
            _merge_opportunity(existing, opp) if existing else opp
        )

    try:
        with open(_OPPORTUNITIES_FILE, "w") as f:
            json.dump(
                {
                    opp.source_hash: opp.model_dump()
                    for opp in existing_by_hash.values()
                },
                f,
                indent=4,
                default=str,
            )
        return True
    except Exception as e:
        print(f"Error saving opportunities: {e}")
        return False
