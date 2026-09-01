"""state.py — the agent's working memory for a single task run.

Plain TypedDict (LangGraph-native): fields annotated with `operator.add` are
grown by concatenation every time a node returns a partial update for them;
all other fields are simply overwritten by whatever a node returns.
"""

import operator
from typing import Annotated, Any, Dict, List, NotRequired, Optional, TypedDict


class RoutingDecisionDict(TypedDict):
    task_type: str
    model_role: str
    tools_needed: List[str]
    reason: str


class PlanStep(TypedDict):
    step_num: int
    tool: str
    input: str
    status: str  # pending | done | error


class StepOutput(TypedDict):
    step_num: int
    tool: str
    input: str
    output: str
    error: bool
    sources: NotRequired[List[Dict[str, str]]]  # populated by the real 'search' tool (Phase 4)


class TraceEntry(TypedDict):
    role: str  # thought | action | observation
    content: str


class AgentState(TypedDict):
    task_id: str
    original_task: str
    routing_decision: Optional[RoutingDecisionDict]

    plan: List[PlanStep]
    current_step: int

    step_outputs: Annotated[List[StepOutput], operator.add]
    messages: Annotated[List[Dict[str, str]], operator.add]
    trace: Annotated[List[TraceEntry], operator.add]

    status: str  # planning | executing | revising | complete | failed
    revise_count: int
    final_answer: Optional[str]
