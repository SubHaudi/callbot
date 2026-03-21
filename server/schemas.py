"""Request/response schemas for the callbot server (FR-012)."""

import re
from dataclasses import dataclass
from typing import Optional

_UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@dataclass
class TurnRequest:
    """Validated turn request model.

    - text: 1~2000 characters, required
    - session_id: UUID format if provided
    - caller_id: max 20 characters if provided
    """
    text: str
    session_id: Optional[str] = None
    caller_id: Optional[str] = None

    def validate(self) -> list:
        """Return list of error dicts. Empty list = valid."""
        errors = []
        if self.text is None or len(self.text) < 1:
            errors.append({
                "loc": ["body", "text"],
                "msg": "text is required and must be at least 1 character",
                "type": "value_error",
            })
            return errors  # early return — no point checking length
        if len(self.text) > 2000:
            errors.append({
                "loc": ["body", "text"],
                "msg": "ensure this value has at most 2000 characters",
                "type": "value_error",
            })
        if self.session_id is not None and not _UUID_REGEX.match(self.session_id):
            errors.append({
                "loc": ["body", "session_id"],
                "msg": "session_id must be a valid UUID",
                "type": "value_error",
            })
        if self.caller_id is not None and len(self.caller_id) > 20:
            errors.append({
                "loc": ["body", "caller_id"],
                "msg": "caller_id must be at most 20 characters",
                "type": "value_error",
            })
        return errors
