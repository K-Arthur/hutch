"""Generated-document pipeline: durable storage, format generators, and preview rendering.

The storage layer (``documents.storage``) owns the immutable version tree under
``<state>/documents``; ``documents.docgen`` renders typed content specifications into
bytes and validates them before a version may be promoted; the ``create_document`` /
``revise_document`` / ``inspect_document`` tools expose the capability to runs.
"""

from .storage import (
    DOCUMENT_FORMATS,
    MIME_BY_FORMAT,
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENTS_PER_RUN,
    DocumentIntegrityError,
    DocumentStorage,
    DocumentStorageError,
    StagedDocument,
    new_document_id,
    reconcile_documents_store,
    sanitize_storage_name,
)

__all__ = [
    "DOCUMENT_FORMATS",
    "MIME_BY_FORMAT",
    "MAX_DOCUMENT_BYTES",
    "MAX_DOCUMENTS_PER_RUN",
    "DocumentIntegrityError",
    "DocumentStorage",
    "DocumentStorageError",
    "StagedDocument",
    "new_document_id",
    "reconcile_documents_store",
    "sanitize_storage_name",
]
