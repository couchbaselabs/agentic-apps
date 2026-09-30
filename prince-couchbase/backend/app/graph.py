"""The PRINCE workflow as a LangGraph state machine (harness engineering).

    clarify ──(needs clarification?)──► END (ask user)
        │ no
        ▼
    think_plan ──► researcher ──► reflection ──(sufficient?)──► writer ──► END
                        ▲                          │ no
                        └──────── follow-ups ──────┘

State is persisted at every super-step by CouchbaseSaver (collection
`checkpoints`), so a failed run resumes from the failed node.
"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from .schema import PrinceState
from .agents import nodes
from .checkpointer import CouchbaseSaver


def _after_clarify(state: PrinceState) -> str:
    return "ask_user" if state.get("needs_clarification") else "think_plan"


def _after_reflection(state: PrinceState) -> str:
    return "writer" if state.get("sufficient", True) else "researcher"


def build_graph(checkpointer: bool = True):
    g = StateGraph(PrinceState)

    g.add_node("clarify", nodes.clarify)
    g.add_node("think_plan", nodes.think_plan)
    g.add_node("researcher", nodes.researcher)
    g.add_node("reflection", nodes.reflection)
    g.add_node("writer", nodes.writer)

    g.set_entry_point("clarify")
    g.add_conditional_edges("clarify", _after_clarify,
                            {"ask_user": END, "think_plan": "think_plan"})
    g.add_edge("think_plan", "researcher")
    g.add_edge("researcher", "reflection")
    g.add_conditional_edges("reflection", _after_reflection,
                            {"writer": "writer", "researcher": "researcher"})
    g.add_edge("writer", END)

    saver = CouchbaseSaver() if checkpointer else None
    return g.compile(checkpointer=saver)


# Lazily built so importing this module never forces a DB connection.
_GRAPH = None


def get_graph(checkpointer: bool = True):
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph(checkpointer=checkpointer)
    return _GRAPH
