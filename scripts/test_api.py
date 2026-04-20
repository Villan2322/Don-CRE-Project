"""
Test the API endpoint directly using httpx.
"""
import asyncio
import httpx
import os

async def test_api():
    print("=" * 60)
    print("API ENDPOINT TEST")
    print("=" * 60)
    
    # The API is running on the Vercel dev server
    # We'll test the health endpoint first
    base_url = "http://localhost:3000/api"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Test health endpoint
        print("\n1. Testing /api/health...")
        try:
            resp = await client.get(f"{base_url}/health")
            print(f"   Status: {resp.status_code}")
            print(f"   Response: {resp.json()}")
        except Exception as e:
            print(f"   Error: {e}")
            print("   (Backend may not be running on port 3000)")
        
        # Test agents endpoint
        print("\n2. Testing /api/agents...")
        try:
            resp = await client.get(f"{base_url}/agents")
            print(f"   Status: {resp.status_code}")
            data = resp.json()
            print(f"   Pipeline: {data.get('pipeline_architecture')}")
            print(f"   Stages: {len(data.get('stages', []))}")
        except Exception as e:
            print(f"   Error: {e}")
    
    print("\n" + "=" * 60)
    print("API test complete")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_api())
