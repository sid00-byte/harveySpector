import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres.yyoqyacghfemgmcyexxk:pYjgyz-nuxtew-7wisjo@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

async def main():
    print("Connecting to live production Supabase instance...")
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        print("Checking/creating full-text search GIN index...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_act_chunks_fts
            ON act_chunks USING gin(to_tsvector('english', text));
        """)
        print("✓ GIN index verified.")

        print("Checking/creating vector cosine similarity IVFFlat index...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_act_chunks_embedding
            ON act_chunks USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 50);
        """)
        print("✓ IVFFlat index verified.")

        print("Checking/creating section_number index...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_act_chunks_sec_num ON act_chunks (section_number);
        """)
        print("✓ Section number index verified.")

        print("Checking/creating chapter_number index...")
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_act_chunks_chap_num ON act_chunks (chapter_number);
        """)
        print("✓ Chapter number index verified.")

        print("\nAll database performance indexes are active and optimized!")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
