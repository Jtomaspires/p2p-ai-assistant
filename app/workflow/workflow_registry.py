"""WorkflowRegistry — maps workflow names to Workflow subclasses (Launchpad pattern).

v1: single entry. Day 3+ can add APPROVAL, SEND, etc.
"""

from enum import Enum

from app.workflow.ticket_workflow import TicketWorkflow


class WorkflowRegistry(Enum):
    TICKET = TicketWorkflow
