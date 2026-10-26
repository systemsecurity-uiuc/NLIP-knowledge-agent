"""Adapter for systemsecurity-uiuc/NLIP-security-extensions.

Install the lab framework on PYTHONPATH before loading this optional module.
The core guard remains usable without the SDK.
"""

from nlip_sdk.nlip_security_extensions import (
    EnforcementPoint,
    SecurityDecision,
    SecurityEvent,
    SecurityExtension,
)

from .guard import SecurityGuard


class KnowledgeSecurityExtension(SecurityExtension):
    """Apply the same policy at SDK client and server communication boundaries."""

    def __init__(self, policy_path: str | None = None) -> None:
        self.guard = SecurityGuard.from_policy_file(policy_path)

    async def evaluate(self, event: SecurityEvent) -> SecurityDecision:
        message = event.message.model_dump(mode="json", exclude_none=True)
        # Requests leave clients and enter servers; responses travel the reverse path.
        is_request = (
            event.component == "server" and event.point == EnforcementPoint.INGRESS
        ) or (
            event.component == "client" and event.point == EnforcementPoint.EGRESS
        )
        inspect = self.guard.inspect_inbound if is_request else self.guard.inspect_outbound
        decision = inspect(message)
        if decision.allowed:
            return SecurityDecision.allow()
        return SecurityDecision.block("; ".join(decision.reasons))
