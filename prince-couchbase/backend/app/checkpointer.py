"""CouchbaseSaver — a LangGraph checkpointer backed by Couchbase.

This is the direct replacement for PRINCE's PostgreSQL LangGraph checkpointer.
Every step of the graph persists its state to the `checkpoints` collection, so a
run that fails midway can be resumed from the failed node (the article's
"user-initiated retry that skips previously successful steps").

Implements the LangGraph BaseCheckpointSaver contract (sync). Serialization uses
LangGraph's JsonPlusSerializer; opaque bytes are base64-encoded into JSON docs so
they store cleanly as Couchbase documents.
"""
from __future__ import annotations

import base64
from typing import Any, Iterator, Optional, Sequence

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from .config import settings
from .couchbase_client import kv_get, kv_upsert, query


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode())


class CouchbaseSaver(BaseCheckpointSaver):
    def __init__(self) -> None:
        super().__init__()
        self.serde = JsonPlusSerializer()
        self.coll = settings.coll_checkpoints

    # ---- key helpers ----
    @staticmethod
    def _ckpt_key(thread_id: str, ns: str, checkpoint_id: str) -> str:
        return f"ckpt::{thread_id}::{ns}::{checkpoint_id}"

    @staticmethod
    def _latest_key(thread_id: str, ns: str) -> str:
        return f"latest::{thread_id}::{ns}"

    @staticmethod
    def _writes_key(thread_id: str, ns: str, checkpoint_id: str, task_id: str, idx: int) -> str:
        return f"writes::{thread_id}::{ns}::{checkpoint_id}::{task_id}::{idx}"

    # ---- write path ----
    def put(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> dict[str, Any]:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]

        type_, ser = self.serde.dumps_typed(checkpoint)
        mtype, mser = self.serde.dumps_typed(metadata)
        doc = {
            "type": "checkpoint",
            "thread_id": thread_id,
            "checkpoint_ns": ns,
            "checkpoint_id": checkpoint_id,
            "parent_checkpoint_id": config["configurable"].get("checkpoint_id"),
            "checkpoint_type": type_,
            "checkpoint_b64": _b64(ser),
            "metadata_type": mtype,
            "metadata_b64": _b64(mser),
        }
        kv_upsert(self.coll, self._ckpt_key(thread_id, ns, checkpoint_id), doc)
        kv_upsert(self.coll, self._latest_key(thread_id, ns), {"checkpoint_id": checkpoint_id})
        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: dict[str, Any],
        writes: Sequence[tuple[str, Any]],
        task_id: str,
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"]["checkpoint_id"]
        for idx, (channel, value) in enumerate(writes):
            vtype, vser = self.serde.dumps_typed(value)
            doc = {
                "type": "checkpoint_write",
                "thread_id": thread_id,
                "checkpoint_ns": ns,
                "checkpoint_id": checkpoint_id,
                "task_id": task_id,
                "idx": idx,
                "channel": channel,
                "value_type": vtype,
                "value_b64": _b64(vser),
            }
            kv_upsert(self.coll, self._writes_key(thread_id, ns, checkpoint_id, task_id, idx), doc)

    # ---- read path ----
    def _load_writes(self, thread_id: str, ns: str, checkpoint_id: str) -> list[tuple[str, str, Any]]:
        rows = query(
            f"SELECT task_id, channel, value_type, value_b64, idx FROM {settings.coll_checkpoints} "
            f"WHERE type = \"checkpoint_write\" AND thread_id = $t AND checkpoint_ns = $ns "
            f"AND checkpoint_id = $c ORDER BY idx",
            {"t": thread_id, "ns": ns, "c": checkpoint_id},
        )
        out = []
        for r in rows:
            val = self.serde.loads_typed((r["value_type"], _unb64(r["value_b64"])))
            out.append((r["task_id"], r["channel"], val))
        return out

    def get_tuple(self, config: dict[str, Any]) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = get_checkpoint_id(config)
        if not checkpoint_id:
            latest = kv_get(self.coll, self._latest_key(thread_id, ns))
            if not latest:
                return None
            checkpoint_id = latest["checkpoint_id"]

        doc = kv_get(self.coll, self._ckpt_key(thread_id, ns, checkpoint_id))
        if not doc:
            return None
        checkpoint = self.serde.loads_typed((doc["checkpoint_type"], _unb64(doc["checkpoint_b64"])))
        metadata = self.serde.loads_typed((doc["metadata_type"], _unb64(doc["metadata_b64"])))
        writes = self._load_writes(thread_id, ns, checkpoint_id)
        parent = doc.get("parent_checkpoint_id")
        parent_config = (
            {"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": parent}}
            if parent else None
        )
        return CheckpointTuple(
            config={"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": checkpoint_id}},
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=writes,
        )

    def list(
        self,
        config: Optional[dict[str, Any]],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"] if config else None
        ns = config["configurable"].get("checkpoint_ns", "") if config else ""
        lim = f"LIMIT {int(limit)}" if limit else ""
        rows = query(
            f"SELECT checkpoint_id FROM {settings.coll_checkpoints} "
            f"WHERE type = \"checkpoint\" AND thread_id = $t AND checkpoint_ns = $ns {lim}",
            {"t": thread_id, "ns": ns},
        )
        for r in rows:
            cfg = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ns, "checkpoint_id": r["checkpoint_id"]}}
            t = self.get_tuple(cfg)
            if t:
                yield t
