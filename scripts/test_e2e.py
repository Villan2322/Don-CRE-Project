"""
End-to-end test of the CRE pipeline with actual AI calls.
"""
import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from services.pipeline import CREPipeline

# Sample rent roll text (simulating extracted PDF content)
SAMPLE_RENT_ROLL = """
RENT ROLL - 5041 Bayou Boulevard
As of April 1, 2026

Tenant Name          Suite    RSF      Monthly Rent    Annual Rent    Lease Start    Lease End
------------------------------------------------------------------------------------------
Acme Corporation     101      12,500   $26,041.67      $312,500       01/01/2023     12/31/2027
Beta Industries      102      8,750    $16,406.25      $196,875       03/01/2024     02/28/2029
Coastal Medical      201      15,000   $31,250.00      $375,000       06/01/2022     05/31/2027
Delta Services       202      6,200    $11,625.00      $139,500       09/01/2023     08/31/2028
Echo Partners        301      9,800    $18,375.00      $220,500       01/01/2025     12/31/2029
------------------------------------------------------------------------------------------
TOTALS                        52,250   $103,697.92     $1,244,375

Average Rent PSF: $23.82
Occupancy: 87.1%
"""

async def run_test():
    print("=" * 60)
    print("CRE PIPELINE END-TO-END TEST")
    print("=" * 60)
    
    # Check API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        return False
    print(f"API Key: {api_key[:20]}...{api_key[-4:]}")
    
    # Initialize pipeline
    print("\n1. Initializing pipeline...")
    pipeline = CREPipeline()
    print("   Pipeline initialized")
    
    # Create test document
    print("\n2. Creating test document...")
    test_files = [
        {
            "filename": "rent_roll_2026.pdf",
            "content": SAMPLE_RENT_ROLL.encode('utf-8'),
            "content_type": "application/pdf",
        }
    ]
    print(f"   Created 1 test file: rent_roll_2026.pdf")
    
    # Set Property Appraiser SF baseline
    # Note: Rent roll shows 52,250 SF occupied, PA shows 60,000 SF total
    # This means ~7,750 SF discrepancy (potential recovery)
    property_appraiser_sf = 60000.0
    print(f"\n3. Property Appraiser SF Baseline: {property_appraiser_sf:,.0f} SF")
    print(f"   (Rent Roll shows 52,250 SF - expecting ~7,750 SF discrepancy)")
    
    # Run pipeline
    print("\n4. Running pipeline analysis...")
    print("-" * 40)
    
    try:
        result = await pipeline.analyze(
            files=test_files,
            deal_name="5041 Bayou Boulevard Test",
            property_appraiser_sf=property_appraiser_sf
        )
        
        print("-" * 40)
        print("\n5. RESULTS:")
        print("-" * 40)
        
        if result.get("success"):
            print(f"   Status: SUCCESS")
            print(f"   Deal Name: {result.get('deal_name')}")
            print(f"   Documents Processed: {result.get('documents_processed')}")
            
            # RSF Analysis
            print(f"\n   RSF ANALYSIS:")
            pa_sf = result.get('property_appraiser_sf')
            print(f"   - Property Appraiser SF: {pa_sf:,.0f}" if isinstance(pa_sf, (int, float)) else f"   - Property Appraiser SF: {pa_sf}")
            rsf_rec = result.get('rsf_recovery_sf', 0) or 0
            print(f"   - RSF Recovery SF: {rsf_rec:,.0f}" if isinstance(rsf_rec, (int, float)) else f"   - RSF Recovery SF: {rsf_rec}")
            rsf_val = result.get('rsf_recovery_annual_value', 0) or 0
            print(f"   - RSF Recovery Value: ${rsf_val:,.0f}/year" if isinstance(rsf_val, (int, float)) else f"   - RSF Recovery Value: {rsf_val}")
            
            # Score
            print(f"\n   DEAL SCORE:")
            print(f"   - Score: {result.get('score', 'N/A')}")
            print(f"   - Tier: {result.get('tier', 'N/A')}")
            
            # Red flags
            flags = result.get('red_flags', [])
            print(f"\n   RED FLAGS: {len(flags)} found")
            for flag in flags[:3]:
                if isinstance(flag, dict):
                    print(f"   - [{flag.get('severity', 'UNKNOWN')}] {flag.get('title', flag.get('message', 'No title'))}")
            
            # Trace log
            trace = result.get('trace_log', [])
            print(f"\n   TRACE LOG: {len(trace)} entries")
            for log in trace[-5:]:
                print(f"   [{log.get('stage')}] {log.get('message')}")
            
            # RSF Analysis details
            rsf_analysis = result.get('rsf_analysis', {})
            print(f"\n   RSF ANALYSIS DETAILS:")
            print(f"   - Reconciliation: {rsf_analysis.get('reconciliation', {})}")
            print(f"   - Recovery Opportunity: {rsf_analysis.get('recovery_opportunity', {})}")
            print(f"   - Discrepancy Found: {rsf_analysis.get('discrepancy_found')}")
            
            print("\n" + "=" * 60)
            print("TEST PASSED - Pipeline executed successfully!")
            print("=" * 60)
            return True
        else:
            print(f"   Status: FAILED")
            print(f"   Error: {result.get('error')}")
            if result.get('traceback'):
                print(f"\n   Traceback:\n{result.get('traceback')[:500]}")
            return False
            
    except Exception as e:
        import traceback
        print(f"\n   EXCEPTION: {e}")
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = asyncio.run(run_test())
    sys.exit(0 if success else 1)
