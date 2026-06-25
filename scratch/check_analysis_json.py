import asyncio
import os
import asyncpg
import json

DATABASE_URL = "postgresql://postgres.yyoqyacghfemgmcyexxk:pYjgyz-nuxtew-7wisjo@aws-1-us-east-1.pooler.supabase.com:5432/postgres"

async def main():
    print("Connecting to Supabase...")
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("Connected!")
        
        # Get the latest analysis
        row = await conn.fetchrow("""
            SELECT id, "caseId", status, "complianceScore", report 
            FROM analyses 
            ORDER BY "createdAt" DESC 
            LIMIT 1;
        """)
        
        if row:
            print(f"\nAnalysis ID: {row['id']}")
            print(f"Case ID: {row['caseId']}")
            print(f"Status: {row['status']}")
            print(f"Compliance Score: {row['complianceScore']}")
            
            report_str = row['report']
            if report_str:
                report = json.loads(report_str) if isinstance(report_str, str) else report_str
                print("\nReport JSON:")
                print(json.dumps(report, indent=2))
            else:
                print("\nNo report JSON found in this record.")
        else:
            print("\nNo analysis records found.")
            
        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
