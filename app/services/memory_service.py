from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    QueryRequest,
)
from fastembed import TextEmbedding
import uuid
import logging
import asyncio
from app.core.config import settings

logger = logging.getLogger(__name__)

client = None
embedding_model = None

COLLECTION_NAME = "users_memory"


def setup_memory_service():
    """Initialize Qdrant client and Embedding model, and ensure collection exists."""
    global client, embedding_model

    if client is not None:
        return

    if settings.QDRANT_URL:
        client = QdrantClient(
            url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=30.0
        )
        logger.info("Initialized QdrantClient with Cloud/URL (timeout=30.0s).")
    else:
        client = QdrantClient(path="qdrant_data")
        logger.info("Initialized QdrantClient with local path.")

    embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    try:
        if not client.collection_exists(COLLECTION_NAME):
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
            # Create payload indices for fast filtering and deletion
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="user_id",
                field_schema="keyword",
            )
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="message_id",
                field_schema="keyword",
            )
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="session_id",
                field_schema="keyword",
            )
    except Exception as e:
        logger.exception("Error checking/creating Qdrant collection or indices")


async def store_facts(
    user_id: str, facts: list[str], message_id: str = None, session_id: str = None
):
    """Embed and store a list of facts for a given user off the main event loop."""
    if not facts:
        return

    def _sync_store():
        embeddings = list(embedding_model.embed(facts))

        search_requests = [
            QueryRequest(
                query=emb.tolist(),
                filter=Filter(
                    must=[
                        FieldCondition(key="user_id", match=MatchValue(value=user_id))
                    ]
                ),
                limit=1,
                with_payload=False,
            )
            for emb in embeddings
        ]

        try:
            batch_results = client.query_batch_points(
                collection_name=COLLECTION_NAME, requests=search_requests
            )
        except Exception as e:
            logger.exception(
                "Failed to search batch for deduplication", extra={"user_id": user_id}
            )
            batch_results = [[] for _ in embeddings]

        points = []
        SIMILARITY_THRESHOLD = 0.92

        for i, (fact, embedding) in enumerate(zip(facts, embeddings)):
            results = batch_results[i]
            is_duplicate = False
            points_list = results.points if hasattr(results, "points") else results
            for res in points_list:
                if getattr(res, "score", 0) >= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            payload = {"user_id": user_id, "document": fact}
            if message_id:
                payload["message_id"] = message_id
            if session_id:
                payload["session_id"] = session_id

            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist(),
                    payload=payload,
                )
            )

        if points:
            client.upsert(collection_name=COLLECTION_NAME, points=points)

    await asyncio.to_thread(_sync_store)
    logger.info(f"Stored {len(facts)} facts for user {user_id}")


async def retrieve_relevant_facts(
    user_id: str, query: str, limit: int = 5
) -> list[str]:
    """Retrieve facts related to the query for the specific user off the main event loop."""

    def _sync_retrieve():
        query_embedding = list(embedding_model.embed([query]))[0].tolist()
        return client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=limit,
        )

    for attempt in range(2):
        try:
            results = await asyncio.to_thread(_sync_retrieve)
            RETRIEVAL_THRESHOLD = 0.50
            facts = [
                res.payload.get("document")
                for res in results.points
                if res.payload
                and "document" in res.payload
                and getattr(res, "score", 0) >= RETRIEVAL_THRESHOLD
            ]
            return facts
        except Exception as e:
            logger.exception(
                f"Attempt {attempt+1} - Failed to retrieve facts from Qdrant",
                extra={"user_id": user_id, "query": query},
            )
            if attempt == 1:
                return []


async def delete_facts_by_message(user_id: str, message_id: str):
    """Delete all facts associated with a specific message off the main event loop."""

    def _sync_delete():
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(
                        key="message_id", match=MatchValue(value=message_id)
                    ),
                ]
            ),
        )

    try:
        await asyncio.to_thread(_sync_delete)
        logger.info(f"Deleted facts for message {message_id}")
    except Exception as e:
        logger.exception(
            "Failed to delete facts for message from Qdrant",
            extra={"user_id": user_id, "message_id": message_id},
        )


async def delete_facts_by_session(user_id: str, session_id: str):
    """Delete all facts associated with a specific session off the main event loop."""

    def _sync_delete():
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(
                        key="session_id", match=MatchValue(value=session_id)
                    ),
                ]
            ),
        )

    try:
        await asyncio.to_thread(_sync_delete)
        logger.info(f"Deleted facts for session {session_id}")
    except Exception as e:
        logger.exception(
            "Failed to delete facts for session from Qdrant",
            extra={"user_id": user_id, "session_id": session_id},
        )


async def delete_all_facts_for_user(user_id: str):
    """Delete all facts associated with a user off the main event loop."""

    def _sync_delete():
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                ]
            ),
        )

    try:
        await asyncio.to_thread(_sync_delete)
        logger.info(f"Deleted all facts for user {user_id}")
    except Exception as e:
        logger.exception(
            "Failed to delete all facts for user from Qdrant",
            extra={"user_id": user_id},
        )
