import asyncio
import asyncpg

DATABASE_URL = "postgresql://postgres.yyoqyacghfemgmcyexxk:pYjgyz-nuxtew-7wisjo@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        count = await conn.fetchval('SELECT count(*) FROM act_chunks;')
        print(f"Total act_chunks: {count}")
        if count > 0:
            sample = await conn.fetchrow('SELECT section_number, section_title, text FROM act_chunks LIMIT 1;')
            print(f"Sample Chunk: Sec {sample['section_number']} - {sample['section_title']}")
            print(f"Preview: {sample['text'][:150]}...")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
