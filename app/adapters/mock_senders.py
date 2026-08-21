"""Sender directory + routing rules from Day 0 fixtures."""

import json
from pathlib import Path

from app.domain.enums import SenderType
from app.domain.models import RoutingRule, Sender
from app.ports.sender_directory_port import SenderDirectoryPort

ROOT = Path(__file__).resolve().parent.parent.parent
DIRECTORY_PATH = ROOT / "fixtures" / "senders" / "directory.json"

_SENDER_TYPE_MAP = {
    "external_supplier": SenderType.EXTERNAL_SUPPLIER,
    "internal_group": SenderType.INTERNAL_SHAREHOLDER,
    "internal_shareholder": SenderType.INTERNAL_SHAREHOLDER,
    "p2p_contact": SenderType.GROUP_P2P,
    "group_p2p": SenderType.GROUP_P2P,
}


def _domain_of(email: str) -> str:
    return email.rsplit("@", 1)[-1].lower()


class MockSenderDirectory(SenderDirectoryPort):
    def __init__(self, path: Path = DIRECTORY_PATH) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.senders: list[Sender] = []
        for index, raw in enumerate(payload.get("senders", []), start=1):
            self.senders.append(
                Sender(
                    id=f"sender-{index}",
                    email=raw["email"].lower(),
                    name=raw["name"],
                    company=raw["company"],
                    vendor_sap_id=raw.get("vendor_sap_id"),
                    sender_type=_SENDER_TYPE_MAP.get(raw.get("type", ""), SenderType.UNKNOWN),
                )
            )
        self.rules: list[RoutingRule] = [
            RoutingRule(
                id=raw["id"],
                operator_id=raw["operator_id"],
                email=raw.get("email"),
                domain=raw.get("domain"),
            )
            for raw in payload.get("routing_rules", [])
        ]

    def get_by_email(self, email: str) -> Sender | None:
        needle = email.lower()
        return next((sender for sender in self.senders if sender.email == needle), None)

    def get_by_domain(self, domain: str) -> list[Sender]:
        needle = domain.lower()
        return [sender for sender in self.senders if _domain_of(sender.email) == needle]

    def get_routing_rule_by_email(self, email: str) -> RoutingRule | None:
        needle = email.lower()
        return next((rule for rule in self.rules if rule.email and rule.email.lower() == needle), None)

    def get_routing_rule_by_domain(self, domain: str) -> RoutingRule | None:
        needle = domain.lower()
        return next((rule for rule in self.rules if rule.domain and rule.domain.lower() == needle), None)
