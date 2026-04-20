"""
Quick end-to-end test of the CRE pipeline backend.
Tests with a sample rent roll to verify the full flow works.
"""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.pipeline import CREPipeline


# Sample rent roll data (simulating extracted text from a PDF)
SAMPLE_RENT_ROLL = """
RENT ROLL - 5041 Bayou Boulevard
As of April 2026

Suite    Tenant Name              RSF        Monthly Rent    Lease Start    Lease End
-------------------------------------------------------------------------------------
101      ABC Corporation          5,200      $13,000         01/01/2024     12/31/2028
102      XYZ Industries           3,800      $9,500          06/01/2023     05/31/2027
103      Smith & Associates       2,400      $6,000          03/01/2025     02/28/2030
104      Tech Startup LLC         1,800      $4,950          09/01/2024     08/31/2027
105      Medical Group            4,500      $12,375         01/01/2022     12/31/2026
106      Law Offices of Johnson   2,100      $5,775          04/01/2024     03/31/2029
107      Consulting Partners      3,200      $8,800          07/01/2023     06/30/2028
-------------------------------------------------------------------------------------
TOTAL OCCUPIED:                  23,000     $60,400

VACANT:
108      (Vacant)                 2,000      -               -              -

TOTAL BUILDING RSF:              25,000
OCCUPANCY:                       92%
"""


async def test_pipeline():
    print("=" * 60)
    print("CRE Pipeline Backend Test")
    print("=" * 60)
    
    # Check OpenRouter API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("\nERROR: OPENROUTER_API_KEY not set!")
        print("Please set the environment variable and try again.")
        return False
    
    print(f"\nAPI Key: {api_key[:10]}...{api_key[-4:]}")
    
    # Initialize pipeline
    print("\n1. Initializing pipeline...")
    pipeline = CREPipeline()
    print("   OK - Pipeline initialized")
    
    # Create test file data
    print("\n2. Preparing test document...")
    test_files = [{
        "filename": "rent_roll_5041_bayou.txt",
        "content": SAMPLE_RENT_ROLL.encode('utf-8'),
        "content_type": "text/plain",
    }]
    print(f"   OK - Test file: {test_files[0]['filename']}")
    
    # Run analysis with Property Appraiser baseline
    # The PA says the building is 26,500 SF, but rent roll only shows 25,000 SF
    # This should flag a 1,500 SF discrepancy
    property_appraiser_sf = 26500.0
    
    print(f"\n3. Running analysis...")
    print(f"   Property Appraiser SF (baseline): {property_appraiser_sf:,.0f}")
    print(f"   Rent Roll shows: 25,000 SF")
    print(f"   Expected discrepancy: 1,500 SF")
    print("\n   Calling pipeline.analyze()...")
    
    try:
        result = await pipeline.analyze(
            files=test_files,
            deal_name="5041 Bayou Boulevard Test",
            property_appraiser_sf=property_appraiser_sf
        )
    except Exception as e:
        print(f"\n   ERROR during analysis: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Check result
    print("\n4. Checking results...")
    
    if not result.get("success"):
        print(f"   FAILED: {result.get('error', 'Unknown error')}")
        if result.get("traceback"):
            print(f"\n   Traceback:\n{result['traceback']}")
        return False
    
    print("   OK - Analysis succeeded!")
    
    # Print key results
    print(f"\n5. Analysis Results:")
    print(f"   Deal Name: {result.get('deal_name', 'N/A')}")
    print(f"   Documents Processed: {result.get('documents_processed', 0)}")
    print(f"   Deal Score: {result.get('score', 'N/A')} ({result.get('tier', 'N/A')})")
    
    rsf_recovery = result.get("rsf_recovery_sf", 0)
    rsf_value = result.get("rsf_recovery_annual_value", 0)
    print(f"\n   RSF Recovery Opportunity:")
    print(f"   - Discrepancy SF: {rsf_recovery:,.0f}")
    print(f"   - Annual Value: ${rsf_value:,.0f}")
    
    # Print trace log
    trace_log = result.get("trace_log", [])
    if trace_log:
        print(f"\n6. Pipeline Trace ({len(trace_log)} entries):")
        for log in trace_log[-10:]:  # Show last 10
            level = log.get("level", "info").upper()
            stage = log.get("stage", "")
            msg = log.get("message", "")
            print(f"   [{level}] {stage}: {msg}")
    
    print("\n" + "=" * 60)
    print("TEST PASSED - Backend is working!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = asyncio.run(test_pipeline())
    sys.exit(0 if success else 1)
