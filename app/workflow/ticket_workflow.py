"""Day 1 TicketWorkflow: nodes 0-5 (Launchpad WorkflowSchema)."""

from app.domain.events import IncomingEmail
from app.workflow.core.schema import NodeConfig, WorkflowSchema
from app.workflow.core.workflow import Workflow
from app.workflow.nodes.ingestion import IngestionNode
from app.workflow.nodes.intent import IntentNode
from app.workflow.nodes.routing import RoutingNode
from app.workflow.nodes.security import SecurityNode
from app.workflow.nodes.sender import SenderIdNode
from app.workflow.nodes.thread import ThreadResolutionNode
from app.workflow.nodes.triage import TriageNode


class TicketWorkflow(Workflow):
    workflow_schema = WorkflowSchema(
        description="P2P Day 1 afternoon — nodes 0–5 (resolution comes Day 2)",
        event_schema=IncomingEmail,
        start=IngestionNode,
        nodes=[
            NodeConfig(node=IngestionNode, connections=[SecurityNode], description="Parse webhook"),
            NodeConfig(node=SecurityNode, connections=[ThreadResolutionNode], description="Whitelist / SPF"),
            NodeConfig(
                node=ThreadResolutionNode,
                connections=[TriageNode],
                description="New vs continuation",
            ),
            NodeConfig(
                node=TriageNode,
                connections=[IntentNode],
                is_router=True,
                description="Discard non-AP mail",
            ),
            NodeConfig(
                node=IntentNode,
                connections=[SenderIdNode],
                is_router=True,
                description="Intent; skip identity when UNKNOWN",
            ),
            NodeConfig(node=SenderIdNode, connections=[RoutingNode], description="Sender lookup"),
            NodeConfig(
                node=RoutingNode,
                connections=[],
                is_router=True,
                description="MINE vs DELEGATE — Day 1 graph ends here",
            ),
        ],
    )
