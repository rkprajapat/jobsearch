import json
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from configs import PROJECT_DATA_DIR

RESUME_DIR = PROJECT_DATA_DIR.joinpath("resume_sections")
RESUME_DIR.mkdir(exist_ok=True)

_META_PATH = Path(__file__).parent.absolute().joinpath("meta.json")


@dataclass(slots=True)
class TimeAwareStatus:
    status: Literal["In Progress", "Completed", "Not Started", "Failed"] = "Not Started"
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    filename: Optional[str] = None

    @property
    def _file_path(self) -> Optional[Path]:
        file_path = None
        if self.filename:
            file_path = RESUME_DIR.joinpath(self.filename)

        # create the file if it doesn't exist
        if file_path and not file_path.exists():
            file_path.touch()

        return file_path

    @property
    def content(self) -> str:
        if not self.filename:
            return ""

        file_path = self._file_path
        if not file_path or not file_path.exists():
            return ""

        return file_path.read_text(encoding="utf-8")

    def complete(self, new_content: str):
        if not self.filename:
            raise ValueError("Filename must be set to update content.")

        file_path = self._file_path
        if not file_path:
            raise ValueError("Invalid file path.")

        file_path.write_text(new_content, encoding="utf-8")
        self.status = "Completed"
        self.last_updated = datetime.now(timezone.utc)

    def mark_in_progress(self):
        self.status = "In Progress"
        self.last_updated = datetime.now(timezone.utc)

    def mark_failed(self):
        self.status = "Failed"
        self.last_updated = datetime.now(timezone.utc)


class ResumeState(BaseModel):
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    header: TimeAwareStatus = field(default=TimeAwareStatus(filename="header.md"))
    experience: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="experience.md")
    )
    functional_skills: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="functional_skills.md")
    )
    technical_skills: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="technical_skills.md")
    )
    leadership_skills: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="leadership_skills.md")
    )
    projects: TimeAwareStatus = field(default=TimeAwareStatus(filename="projects.md"))
    achievements: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="achievements.md")
    )
    certifications: TimeAwareStatus = field(
        default=TimeAwareStatus(filename="certifications.md")
    )
    education: TimeAwareStatus = field(default=TimeAwareStatus(filename="education.md"))
    notes: TimeAwareStatus = field(default=TimeAwareStatus(filename="notes.md"))
    sections_finalized: bool = False

    @classmethod
    def load(cls) -> "ResumeState":
        if not _META_PATH.exists():
            return cls()

        try:
            data = {}
            if content := _META_PATH.read_text(encoding="utf-8"):
                data = json.loads(content)

            # populate the dataclass fields from the loaded data
            return cls.model_validate(data)
        except Exception as e:
            print(f"Error loading resume state: {e}")
            traceback.print_exc()

        return cls()

    def save(self):
        try:
            _META_PATH.write_text(self.model_dump_json(indent=4), encoding="utf-8")
        except Exception as e:
            print(f"Error saving resume state: {e}")
            traceback.print_exc()
