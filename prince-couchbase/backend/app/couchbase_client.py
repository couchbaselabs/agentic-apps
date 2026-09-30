"""Couchbase connection + thin helpers.

A single Cluster is shared process-wide. Works against Couchbase Capella (TLS,
`couchbases://`) out of the box and against a self-managed/local cluster if you
set CB_TLS=false and use `couchbase://`.
"""
from __future__ import annotations

import threading
from datetime import timedelta
from typing import Any, Iterable, Optional

from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions, QueryOptions
from couchbase.exceptions import DocumentNotFoundException

from .config import settings

_lock = threading.Lock()
_cluster: Optional[Cluster] = None


def get_cluster() -> Cluster:
    """Lazily connect and cache the cluster (thread-safe)."""
    global _cluster
    if _cluster is not None:
        return _cluster
    with _lock:
        if _cluster is not None:
            return _cluster
        auth = PasswordAuthenticator(settings.cb_username, settings.cb_password)
        opts = ClusterOptions(auth)
        # Capella works with the connection string alone. For self-managed TLS
        # clusters that need a CA, pass cert_path.
        if settings.cb_cert_path:
            opts = ClusterOptions(auth, cert_path=settings.cb_cert_path)
        cluster = Cluster(settings.cb_connection_string, opts)
        cluster.wait_until_ready(timedelta(seconds=20))
        _cluster = cluster
        return _cluster


def get_scope():
    bucket = get_cluster().bucket(settings.cb_bucket)
    return bucket.scope(settings.cb_scope)


def get_collection(name: str):
    return get_scope().collection(name)


# --------------------------------------------------------------------------
# KV helpers (the "DynamoDB" role: sessions, logs, citations, checkpoints)
# --------------------------------------------------------------------------
def kv_upsert(collection: str, key: str, value: dict[str, Any]) -> None:
    get_collection(collection).upsert(key, value)


def kv_get(collection: str, key: str) -> Optional[dict[str, Any]]:
    try:
        return get_collection(collection).get(key).content_as[dict]
    except DocumentNotFoundException:
        return None


def kv_remove(collection: str, key: str) -> None:
    try:
        get_collection(collection).remove(key)
    except DocumentNotFoundException:
        pass


# --------------------------------------------------------------------------
# SQL++ helpers (the "Athena" role: analytics over structured `studies`)
# --------------------------------------------------------------------------
def query(statement: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Run a positional/named-parameterised SQL++ query at the scope level, so
    bare collection names (e.g. `studies`) resolve inside bucket.scope."""
    scope = get_scope()
    opts = QueryOptions(named_parameters=params) if params else QueryOptions()
    result = scope.query(statement, opts)
    return [row for row in result]


def cluster_query(statement: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Cluster-level query (needs fully-qualified keyspaces). Used by admin tasks."""
    cluster = get_cluster()
    opts = QueryOptions(named_parameters=params) if params else QueryOptions()
    return [row for row in cluster.query(statement, opts)]


def close() -> None:
    global _cluster
    if _cluster is not None:
        _cluster.close()
        _cluster = None
