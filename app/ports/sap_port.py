"""SAP invoice and clearing port."""

from abc import ABC, abstractmethod

from app.domain.models import Invoice


class SAPPort(ABC):
    @abstractmethod
    def get_approval_invoices(self) -> list[Invoice]:
        pass

    @abstractmethod
    def get_posted_invoices(self) -> list[Invoice]:
        pass

    @abstractmethod
    def get_clearing(self, vendor_id: str, document_number: str) -> dict | None:
        pass

    @abstractmethod
    def get_payment_document(self, clearing_document: str) -> dict | None:
        pass
