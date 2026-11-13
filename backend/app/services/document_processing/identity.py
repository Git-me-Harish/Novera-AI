from hashlib import sha256
from uuid import UUID, uuid5


# Permanent namespaces for deterministic Novera document/chunk identities.
# DO NOT regenerate these values.
DOCUMENT_NAMESPACE = UUID("ab9ed7a3-e12b-4feb-bf76-fa510d69a529")
CHUNK_NAMESPACE = UUID("446312c9-af23-4e74-a284-a4faa8f552ba")


def stable_document_id(
    organization_id: UUID,
    file_hash: str,
) -> UUID:
    """
    Generate a deterministic document UUID.

    The same organization + same file hash will always produce
    the same document UUID.
    """
    key = f"{organization_id}:{file_hash}"

    return uuid5(DOCUMENT_NAMESPACE, key)


def stable_chunk_id(
    document_id: UUID,
    chunk_index: int,
    content: str,
) -> UUID:
    """
    Generate a deterministic chunk UUID.

    The same document + chunk position + chunk content will always
    produce the same chunk UUID.
    """
    content_hash = sha256(
        content.strip().encode("utf-8")
    ).hexdigest()

    key = f"{document_id}:{chunk_index}:{content_hash}"

    return uuid5(CHUNK_NAMESPACE, key)