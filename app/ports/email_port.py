"""Inbound email parsing port."""

from abc import ABC, abstractmethod

from app.domain.events import IncomingEmail


class EmailPort(ABC):
    @abstractmethod
    def parse_webhook(self, payload: dict) -> IncomingEmail:
        """Map a raw webhook or fixture payload onto IncomingEmail."""
