"""Sender directory and routing-rule port."""

from abc import ABC, abstractmethod

from app.domain.models import RoutingRule, Sender


class SenderDirectoryPort(ABC):
    @abstractmethod
    def get_by_email(self, email: str) -> Sender | None:
        pass

    @abstractmethod
    def get_by_domain(self, domain: str) -> list[Sender]:
        pass

    @abstractmethod
    def get_routing_rule_by_email(self, email: str) -> RoutingRule | None:
        pass

    @abstractmethod
    def get_routing_rule_by_domain(self, domain: str) -> RoutingRule | None:
        pass
