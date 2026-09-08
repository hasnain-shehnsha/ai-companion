from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from fastembed import TextEmbedding
import uuid
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

if settings.QDRANT_URL:
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
    logger.info("Initialized QdrantClient with Cloud/URL.")
else:
    client = QdrantClient(path="qdrant_data")
    logger.info("Initialized QdrantClient with local path.")

COLLECTION_NAME = "users_memory"

embedding_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")


def init_qdrant():
    """Ensure the collection exists."""
    try:
        if not client.collection_exists(COLLECTION_NAME):
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
    except Exception as e:
        logger.error(f"Error checking/creating Qdrant collection: {e}")


init_qdrant()


async def store_facts(user_id: str, facts: list[str]):
    """Embed and store a list of facts for a given user."""
    if not facts:
        return

    try:
        embeddings = list(embedding_model.embed(facts))
        points = []
        for i, (fact, embedding) in enumerate(zip(facts, embeddings)):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist(),
                    payload={"user_id": user_id, "document": fact},
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        logger.info(f"Stored {len(facts)} facts for user {user_id}")
    except Exception as e:
        logger.error(f"Failed to store facts in Qdrant: {e}")


async def retrieve_relevant_facts(
    user_id: str, query: str, limit: int = 5
) -> list[str]:
    """Retrieve facts related to the query for the specific user."""
    try:
        query_embedding = list(embedding_model.embed([query]))[0].tolist()

        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            query_filter=Filter(
                must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
            ),
            limit=limit,
        )

        facts = [
            res.payload.get("document")
            for res in results.points
            if res.payload and "document" in res.payload
        ]
        return facts
    except Exception as e:
        logger.error(f"Failed to retrieve facts from Qdrant: {e}")
        return []
