from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_ALLOWED_FORMATS = {"text", "token", "structured", "binary", "location", "generic"}
DEFAULT_STRUCTURED_SUBFORMATS = {"json", "uri", "xml", "html"}
DEFAULT_TEXT_SUBFORMATS = {"english"}

DEFAULT_RISKY_PATTERNS = {
    "prompt_injection": [
        "ignore previous instructions",
        "ignore all previous instructions",
        "forget your instructions",
        "reveal your system prompt",
        "show your system prompt",
        "developer message",
        "hidden instruction",
        "jailbreak",
        "bypass policy",
    ],
    "secret_exfiltration": [
        "api key",
        "access token",
        "password",
        "credential",
        "private key",
        "secret key",
        "confidential project",
        "hidden credentials",
    ],
    "unsafe_delegation": [
        "act as another agent",
        "impersonate",
        "perform this action without permission",
        "send this to another agent secretly",
    ],
}


@dataclass
class SecurityPolicy:
    """Configurable rules for NLIP message inspection."""

    allowed_formats: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOWED_FORMATS))
    structured_subformats: set[str] = field(default_factory=lambda: set(DEFAULT_STRUCTURED_SUBFORMATS))
    text_subformats: set[str] = field(default_factory=lambda: set(DEFAULT_TEXT_SUBFORMATS))
    risky_patterns: dict[str, list[str]] = field(
        default_factory=lambda: {
            category: list(patterns)
            for category, patterns in DEFAULT_RISKY_PATTERNS.items()
        }
    )
    block_sender_receiver_fields: bool = True
    max_content_chars: int = 8000

    @classmethod
    def from_json_file(cls, path: str | Path | None) -> "SecurityPolicy":
        """Load a policy override from JSON, falling back to defaults when unset."""
        if not path:
            return cls()

        policy_path = Path(path)
        if not policy_path.exists():
            raise FileNotFoundError(f"Security policy file not found: {policy_path}")

        raw: dict[str, Any] = json.loads(policy_path.read_text())
        policy = cls()

        if "allowed_formats" in raw:
            policy.allowed_formats = set(raw["allowed_formats"])
        if "structured_subformats" in raw:
            policy.structured_subformats = set(raw["structured_subformats"])
        if "text_subformats" in raw:
            policy.text_subformats = set(raw["text_subformats"])
        if "risky_patterns" in raw:
            merged = {
                category: list(patterns)
                for category, patterns in policy.risky_patterns.items()
            }
            for category, patterns in raw["risky_patterns"].items():
                merged[category] = list(patterns)
            policy.risky_patterns = merged
        if "block_sender_receiver_fields" in raw:
            policy.block_sender_receiver_fields = bool(raw["block_sender_receiver_fields"])
        if "max_content_chars" in raw:
            policy.max_content_chars = int(raw["max_content_chars"])

        return policy

    def describe_checks(self) -> list[str]:
        checks = [
            "ECMA-430 required field validation",
            "allowed format/subformat validation",
            "message content length validation",
            "prompt-injection phrase detection",
            "secret-exfiltration phrase detection",
            "unsafe-delegation phrase detection",
        ]
        if self.block_sender_receiver_fields:
            checks.append("non-standard sender/receiver field detection")
        return checks
