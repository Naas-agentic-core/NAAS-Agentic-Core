import functools

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.supabase import SupabaseVectorStore

# Using functools.lru_cache to manage singletons in a thread-safe way
# instead of global mutable variables.


@functools.lru_cache(maxsize=1)
def get_embedding_model():
    """
    Get the embedding model (Cached).
    Uses BAAI/bge-m3 for high-performance multilingual support.
    """
    return HuggingFaceEmbedding(model_name="BAAI/bge-m3")


class LlamaIndexRetriever:
    def __init__(self, db_url: str, collection_name: str = "vectors"):
        self.db_url = db_url
        self.collection_name = collection_name
        self.embed_model = get_embedding_model()

        # Ensure compatibility with 'vecs' (psycopg2)
        postgres_url = db_url.replace("+asyncpg", "")

        self.vector_store = SupabaseVectorStore(
            postgres_connection_string=postgres_url, collection_name=collection_name
        )
        self.index = VectorStoreIndex.from_vector_store(
            vector_store=self.vector_store, embed_model=self.embed_model
        )

    def search(
        self,
        query: str,
        limit: int = 5,
        filters: dict | None = None,
        similarity_threshold: float | None = None,
    ) -> list[NodeWithScore]:
        """
        Semantic search using LlamaIndex with support for Metadata Filters.
        """
        llama_filters = None

        if filters:
            match_filters = []
            if filters.get("year"):
                match_filters.append(ExactMatchFilter(key="year", value=filters["year"]))
            if filters.get("subject"):
                # Normalize/Fuzzy match might be needed upstream, assuming refined subject here
                match_filters.append(ExactMatchFilter(key="subject", value=filters["subject"]))

            if match_filters:
                llama_filters = MetadataFilters(filters=match_filters)

        retriever_kwargs: dict[str, object] = {
            "similarity_top_k": limit,
            "filters": llama_filters,
        }
        if similarity_threshold is not None:
            retriever_kwargs["similarity_cutoff"] = similarity_threshold

        retriever = self.index.as_retriever(**retriever_kwargs)

        return retriever.retrieve(query)


@functools.lru_cache(maxsize=4)
def get_retriever(db_url: str) -> LlamaIndexRetriever:
    """
    Get or create a retriever instance for the given DB URL.
    Cached to avoid recreating heavy connections, but scoped by URL
    to prevent cross-contamination if multiple DBs are used.
    """
    return LlamaIndexRetriever(db_url)
