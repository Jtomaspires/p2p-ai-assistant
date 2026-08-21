"""TicketWorkflow: complete graph (nodes 0–7, Day 2).

Spine:
  IngestionNode → SecurityNode → ThreadResolutionNode (router)
      ↓ new thread                        ↓ continuation
   TriageNode (router)           ResolutionNode
      ↓ AP                              ↓
   IntentNode (router)           DraftNode
      ↓ known intent  ↓ UNKNOWN        ↓
   SenderIdNode    ResolutionNode  HitlNode  (stop)
      ↓
   RoutingNode (router)
      ↓ MINE
   ResolutionNode → DraftNode → HitlNode  (stop)
"""

from app.domain.events import IncomingEmail
from app.workflow.core.schema import NodeConfig, WorkflowSchema
from app.workflow.core.workflow import Workflow
from app.workflow.nodes.draft import DraftNode
from app.workflow.nodes.hitl import HitlNode
from app.workflow.nodes.ingestion import IngestionNode
from app.workflow.nodes.intent import IntentNode
from app.workflow.nodes.resolution import ResolutionNode
from app.workflow.nodes.routing import RoutingNode
from app.workflow.nodes.security import SecurityNode
from app.workflow.nodes.sender import SenderIdNode
from app.workflow.nodes.thread import ThreadResolutionNode
from app.workflow.nodes.triage import TriageNode


class TicketWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="P2P complete workflow — nodes 0–7 (Day 2)",
        event_schema=IncomingEmail,
        start=IngestionNode,
        nodes=[
            NodeConfig(
                node=IngestionNode,
                connections=[SecurityNode],
                description="Parse webhook, create Ticket",
            ),
            NodeConfig(
                node=SecurityNode,
                connections=[ThreadResolutionNode],
                description="Whitelist / SPF check",
            ),
            NodeConfig(
                node=ThreadResolutionNode,
                connections=[TriageNode, ResolutionNode],
                is_router=True,
                description="New thread → Triage; continuation → Resolution",
            ),
            NodeConfig(
                node=TriageNode,
                connections=[IntentNode],
                is_router=True,
                description="Discard non-AP mail",
            ),
            NodeConfig(
                node=IntentNode,
                connections=[SenderIdNode, ResolutionNode],
                is_router=True,
                description="Intent classification; UNKNOWN skips Sender/Routing",
            ),
            NodeConfig(
                node=SenderIdNode,
                connections=[RoutingNode],
                description="Sender lookup",
            ),
            NodeConfig(
                node=RoutingNode,
                connections=[ResolutionNode],
                is_router=True,
                description="MINE → Resolution; DELEGATE → stop",
            ),
            NodeConfig(
                node=ResolutionNode,
                connections=[DraftNode],
                description="Invoice resolution",
            ),
            NodeConfig(
                node=DraftNode,
                connections=[HitlNode],
                description="Generate response draft",
            ),
            NodeConfig(
                node=HitlNode,
                connections=[],
                description="Halt pipeline; await human approval",
            ),
        ],
    )
