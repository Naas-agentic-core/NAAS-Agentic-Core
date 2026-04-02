import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

async def run_census():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[CENSUS] WARNING: DATABASE_URL not found in env.")
        # Try to find it or exit
        db_url = "postgresql://postgres:postgres@localhost:5432/postgres" # Fallback

    print(f"[CENSUS] Backend type: Supabase/Postgres")
    print(f"[CENSUS] Collection/Index name: vectors")
    print(f"[CENSUS] Connection params: {db_url}")

    # We will query directly via vecs or asyncpg since LlamaIndex doesn't provide an easy count without loading
    try:
        import vecs
        postgres_url = db_url.replace("+asyncpg", "")
        vx = vecs.create_client(postgres_url)
        collection = vx.get_collection(name="vectors")

        # Unfortunatly vecs doesn't have an easy "get all" count but we can try to query
        res = collection.query(
            data=[],
            limit=100,
            include_value=True,
            include_metadata=True
        )

        count = len(res)
        print(f"[CENSUS] ══════════════════════════════════════")
        print(f"[CENSUS] TOTAL CHUNKS (approx/limit 100): {count}")
        print(f"[CENSUS] ══════════════════════════════════════")

        if count < 20:
            print(f"🚨🚨🚨 [CENSUS] CRITICAL: ONLY {count} CHUNKS IN ENTIRE DB")
            print(f"🚨🚨🚨 [CENSUS] THIS EXPLAINS WHY ALL QUERIES RETURN THE SAME RESULT")

        sources = {}
        for i, doc in enumerate(res[:10]):
            meta = doc[2] if len(doc) > 2 else {}
            print(f"[CENSUS] Chunk[{i}] id={doc[0]}")
            print(f"[CENSUS]   metadata={meta}")
            print(f"[CENSUS]   ---")
            source = meta.get("source", "unknown")
            sources[source] = sources.get(source, 0) + 1

        print("[CENSUS] UNIQUE SOURCES:")
        for k, v in sources.items():
            print(f"[CENSUS]   {k} -> {v}")

    except Exception as e:
        print(f"[CENSUS] Failed to connect or query: {e}")

if __name__ == "__main__":
    asyncio.run(run_census())
