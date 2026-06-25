import asyncio
import json
import os
import sqlite3
import asyncpg
from typing import Any

DATABASE_URL = os.environ.get("DATABASE_URL")
SQLITE_DB_PATH = "data/harvey_fallback.db"

async def main():
    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL environment variable is not set.")
        return

    print("🚀 Seeding remote database from local fallback SQLite database...")
    print(f"Connection String: {DATABASE_URL[:45]}...")

    if not os.path.exists(SQLITE_DB_PATH):
        print(f"❌ Error: Fallback SQLite database not found at {SQLITE_DB_PATH}")
        return

    # 1. Fetch chunks from SQLite
    print("\n1. Fetching chunks and pre-calculated embeddings from SQLite...")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = sqlite_conn.cursor()
    cursor.execute("""
        SELECT chunk_id, chapter_number, chapter_title,
               section_number, section_title, subsection,
               text, page_number, line_start, line_end,
               related_forms, keywords, embedding
        FROM act_chunks
    """)
    rows = cursor.fetchall()
    sqlite_conn.close()
    print(f"✅ Found {len(rows)} chunks in fallback database.")

    if len(rows) == 0:
        print("❌ No chunks found to migrate.")
        return

    # 2. Connect to remote PostgreSQL
    print("\n2. Connecting to remote PostgreSQL database...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("✅ Connected to remote database.")
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        return

    # 3. Insert chunks into remote PostgreSQL
    print("\n3. Inserting chunks into remote PostgreSQL...")
    try:
        # Enable pgvector if not enabled
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # Truncate existing act_chunks to avoid duplicates
        print("🧹 Truncating remote act_chunks table...")
        await conn.execute("TRUNCATE TABLE act_chunks RESTART IDENTITY CASCADE;")

        # Prepare rows for insert
        insert_rows = []
        for r in rows:
            chunk_id, ch_num, ch_title, sec_num, sec_title, sub, text, pg_num, line_start, line_end, forms_json, keywords_json, emb_json = r
            
            # Parse lists
            forms = json.loads(forms_json) if forms_json else []
            keywords = json.loads(keywords_json) if keywords_json else []
            embedding = json.loads(emb_json) if emb_json else []
            
            # Format vector as string for PostgreSQL pgvector insertion compatibility
            embedding_str = "[" + ",".join(map(str, embedding)) + "]" if embedding else None

            insert_rows.append((
                chunk_id,
                ch_num or "",
                ch_title or "",
                sec_num or "",
                sec_title or "",
                sub,
                text,
                pg_num or 0,
                line_start or 0,
                line_end or 0,
                forms,
                keywords,
                embedding_str
            ))

        print("📤 Uploading records...")
        # Batch insert
        await conn.executemany(
            """
            INSERT INTO act_chunks (
                chunk_id, chapter_number, chapter_title,
                section_number, section_title, subsection,
                text, page_number, line_start, line_end,
                related_forms, keywords, embedding
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13);
            """,
            insert_rows
        )
        print(f"🎉 SUCCESS: Seeded {len(insert_rows)} chunks with vector embeddings directly into Supabase!")

    except Exception as e:
        print(f"❌ Error during database seeding: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
