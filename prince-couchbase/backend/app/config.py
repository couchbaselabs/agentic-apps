"""Central configuration. Everything else imports `settings` from here.

Mirrors PRINCE's separation of concerns but every backing service is Couchbase:
  PostgreSQL (LangGraph checkpointer)  -> Couchbase collection `checkpoints`
  DynamoDB   (app state / logs / cites) -> Couchbase collections `sessions`,`logs`,`citations`
  Amazon Athena (structured metadata)  -> Couchbase collection `studies` (SQL++)
  Amazon S3  (unstructured data lake)   -> Couchbase collection `documents` (KV + FTS)
  OpenSearch (vector store)             -> Couchbase FTS Vector Search index
  "semantic layer" (few-shot SQL)       -> Couchbase collection `sql_examples` (vector)
"""
from __future__ import annotations

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---- Couchbase ----
    cb_connection_string: str = "couchbases://localhost"
    cb_username: str = "Administrator"
    cb_password: str = "password"
    cb_bucket: str = "prince"
    cb_scope: str = "main"
    cb_tls: bool = True
    cb_cert_path: str = ""
    cb_fts_vector_index: str = "prince_documents_vec"
    cb_fts_text_index: str = "prince_documents_text"

    # ---- LLM (OpenAI-compatible) ----
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model_strong: str = "gpt-4o"
    llm_model_fast: str = "gpt-4o-mini"

    llm_fallback_base_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model_strong: str = ""
    llm_fallback_model_fast: str = ""

    embed_base_url: str = "https://api.openai.com/v1"
    embed_api_key: str = ""
    embed_model: str = "text-embedding-3-small"
    embed_dim: int = 1536

    mock_llm: bool = False

    # ---- Observability ----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    # ---- Retrieval tuning ----
    rag_expansions: int = 5
    rag_semantic_weight: float = 0.7
    rag_keyword_weight: float = 0.3
    rag_initial_k: int = 20
    rag_final_k: int = 7
    sql_max_rows: int = 50
    sql_max_retries: int = 3

    # ---- Collections (fixed logical names) ----
    coll_studies: str = "studies"
    coll_documents: str = "documents"
    coll_sql_examples: str = "sql_examples"
    coll_checkpoints: str = "checkpoints"
    coll_sessions: str = "sessions"
    coll_logs: str = "logs"
    coll_citations: str = "citations"
    coll_ner_queue: str = "ner_queue"

    @property
    def keyspace_prefix(self) -> str:
        return f"`{self.cb_bucket}`.`{self.cb_scope}`"

    def keyspace(self, collection: str) -> str:
        return f"`{self.cb_bucket}`.`{self.cb_scope}`.`{collection}`"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
