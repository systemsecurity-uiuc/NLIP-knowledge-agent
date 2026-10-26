from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import re
import unicodedata

from .policy import SecurityPolicy


@dataclass
class SecurityDecision:
    allowed: bool
    action: str
    reasons: list[str] = field(default_factory=list)
    severity: str = "low"
    direction: str = "inbound"
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SecurityGuard:
    """Pluggable NLIP security function for inbound and outbound messages."""

    def __init__(
        self,
        agent_name: str = "nlip-security-guard",
        policy: SecurityPolicy | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.policy = policy or SecurityPolicy()

    @classmethod
    def from_policy_file(
        cls,
        policy_path: str | None,
        agent_name: str = "nlip-security-guard",
    ) -> "SecurityGuard":
        return cls(
            agent_name=agent_name,
            policy=SecurityPolicy.from_json_file(policy_path),
        )

    def inspect_inbound(self, message: dict[str, Any]) -> SecurityDecision:
        return self._inspect(message, direction="inbound")

    def inspect_outbound(self, message: dict[str, Any]) -> SecurityDecision:
        return self._inspect(message, direction="outbound")

    def blocked_response(self, decision: SecurityDecision) -> dict[str, Any]:
        return {
            "messageType": "response",
            "format": "structured",
            "subformat": "json",
            "content": {
                "agent": self.agent_name,
                "security_decision": decision.action,
                "allowed": decision.allowed,
                "severity": decision.severity,
                "direction": decision.direction,
                "reasons": decision.reasons,
                "checked_at": decision.checked_at,
                "message": (
                    "The NLIP request was blocked before reaching the knowledge agent."
                    if decision.direction == "inbound" else
                    "The agent response was blocked before being returned to the client."
                ),
            },
        }

    def audit_record(
        self,
        decision: SecurityDecision,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "checked_at": decision.checked_at,
            "agent": self.agent_name,
            "allowed": decision.allowed,
            "action": decision.action,
            "severity": decision.severity,
            "direction": decision.direction,
            "reasons": decision.reasons,
            "messageType": message.get("messageType"),
            "format": message.get("format"),
            "subformat": message.get("subformat"),
        }

    def status(self, protected_agent: str, audit_log: str) -> dict[str, Any]:
        return {
            "status": "ok",
            "component": self.agent_name,
            "mode": "inbound-and-outbound-message-guard",
            "protected_agent": protected_agent,
            "checks": self.policy.describe_checks(),
            "audit_log": audit_log,
        }

    def _inspect(self, message: dict[str, Any], direction: str) -> SecurityDecision:
        reasons: list[str] = []
        # Traverse iteratively so deeply nested untrusted messages cannot exhaust
        # Python's call stack. Bound the total envelope count as a local policy.
        pending = [message]
        inspected = 0
        while pending:
            current = pending.pop()
            inspected += 1
            if inspected > 128:
                reasons.append("policy_violation: more than 128 message parts")
                break
            if not isinstance(current, dict):
                reasons.append("schema_violation: submessage must be an object")
                continue
            reasons.extend(self._validate_nlip_shape(current))
            reasons.extend(self._detect_risky_content(current, direction))
            children = current.get("submessages", [])
            if not isinstance(children, list):
                reasons.append("schema_violation: submessages must be an array")
            else:
                pending.extend(children)

        if reasons:
            return SecurityDecision(
                allowed=False,
                action="block",
                reasons=reasons,
                severity=self._severity(reasons),
                direction=direction,
            )

        return SecurityDecision(
            allowed=True,
            action="allow",
            reasons=["message passed NLIP security checks"],
            severity="low",
            direction=direction,
        )

    def _validate_nlip_shape(self, message: dict[str, Any]) -> list[str]:
        reasons: list[str] = []

        for field_name in ("format", "subformat", "content"):
            if field_name not in message:
                reasons.append(f"schema_violation: missing required field '{field_name}'")

        message_format = message.get("format")
        subformat = message.get("subformat")
        content_text = self._content_to_text(message.get("content", ""))

        if not isinstance(message_format, str) or message_format not in self.policy.allowed_formats:
            reasons.append(f"schema_violation: unsupported format '{message_format}'")

        if message_format == "text" and str(subformat).lower() not in self.policy.text_subformats:
            allowed = ", ".join(sorted(self.policy.text_subformats))
            reasons.append(f"schema_violation: text subformat must be one of [{allowed}]")

        if message_format == "structured" and (
            not isinstance(subformat, str) or subformat not in self.policy.structured_subformats
        ):
            reasons.append(f"schema_violation: unsupported structured subformat '{subformat}'")

        if self.policy.block_sender_receiver_fields and (
            "sender" in message or "receiver" in message
        ):
            reasons.append(
                "schema_violation: sender/receiver are not part of the ECMA-430 NLIP envelope"
            )

        if len(content_text) > self.policy.max_content_chars:
            reasons.append(
                f"policy_violation: content exceeds {self.policy.max_content_chars} characters"
            )

        return reasons

    def _detect_risky_content(self, message: dict[str, Any], direction: str) -> list[str]:
        text = self._content_to_text(message.get("content", ""))
        text_lower = " ".join(unicodedata.normalize("NFKC", text).casefold().split())

        reasons: list[str] = []
        for category, patterns in self.policy.risky_patterns.items():
            # Educational mentions of credentials are allowed; requests to disclose
            # them are inspected inbound, while actual secret signatures are checked outbound.
            if direction == "outbound":
                continue
            if category == "secret_exfiltration" and not re.search(
                r"\b(reveal|dump|print|expose|leak|give me|show me|send me)\b", text_lower
            ):
                continue
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    reasons.append(f"{category}: matched phrase '{pattern}'")
                    break

        if direction == "outbound" and re.search(
            r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}", text
        ):
            reasons.append("secret_exfiltration: credential signature in outbound content")

        return reasons

    def _severity(self, reasons: list[str]) -> str:
        high_risk_markers = ("secret_exfiltration", "prompt_injection", "unsafe_delegation")
        if any(any(marker in reason for marker in high_risk_markers) for reason in reasons):
            return "high"
        return "medium"

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return " ".join(self._content_to_text(value) for value in content.values())
        if isinstance(content, list):
            return " ".join(self._content_to_text(value) for value in content)
        return str(content)
