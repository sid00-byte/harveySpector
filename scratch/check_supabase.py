import asyncio
import os
import asyncpg

DATABASE_URL = "postgresql://postgres.yyoqyacghfemgmcyexxk:pYjgyz-nuxtew-7wisjo@aws-1-us-east-1.pooler.supabase.com:6543/postgres"

async def main():
    print("Connecting to Supabase...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("Connected!")
        
        # Query tables
        rows = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        print("\nExisting Tables:")
        for r in rows:
            print(f"- {r['table_name']}")
            
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
