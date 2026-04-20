"""
End-to-end tests for the CRE Document Intelligence Pipeline.

Tests the full flow from document upload to analysis output.
"""

import asyncio
import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.pipeline import CREPipeline


async def test_pipeline_with_mock_pdf():
    """Test pipeline with a mock PDF content."""
    print("\n" + "="*60)
    print("TEST 1: Pipeline with mock lease document")
    print("="*60)
    
    pipeline = CREPipeline()
    
    # Simulate a simple lease document text
    mock_lease_content = """
    COMMERCIAL LEASE AGREEMENT
    
    This Lease Agreement is made between:
    Landlord: ABC Properties LLC
    Tenant: Acme Corporation
    
    Property Address: 5041 Bayou Boulevard, Suite 200, Pensacola, FL 32503
    
    LEASE TERMS:
    - Rentable Square Feet: 12,500 RSF
    - Lease Commencement Date: January 1, 2023
    - Lease Expiration Date: December 31, 2028
    - Monthly Base Rent: $15,625.00
    - Annual Base Rent: $187,500.00
    - Rent Per Square Foot: $15.00 PSF
    
    OPERATING EXPENSES:
    - Base Year: 2023
    - CAM Charges: Tenant pays pro-rata share
    - CAM Cap: 5% annual increase
    
    RENEWAL OPTIONS:
    - Two (2) five-year renewal options
    - 90 days written notice required
    
    TENANT IMPROVEMENTS:
    - Landlord TI Allowance: $25.00 PSF ($312,500 total)
    """
    
    # Create mock file data
    files = [{
        "filename": "lease_acme_corp.pdf",
        "content": mock_lease_content.encode('utf-8'),
        "content_type": "application/pdf",
    }]
    
    try:
        result = await pipeline.analyze(files, deal_name="Test Deal - Acme Corp")
        
        print("\n[SUCCESS] Pipeline completed!")
        print("\n--- Analysis Result ---")
        print(json.dumps(result, indent=2, default=str))
        
        # Validate result structure
        assert result.get("success") == True, "Expected success=True"
        assert "analysis" in result, "Missing 'analysis' key"
        
        analysis = result["analysis"]
        
        # Check required fields
        required_fields = ["deal_name", "overall_score", "tier", "documents_processed"]
        for field in required_fields:
            assert field in analysis, f"Missing required field: {field}"
            print(f"  [OK] {field}: {analysis.get(field)}")
        
        # Check arrays are actually arrays
        array_fields = ["tenants", "what_to_get_next", "red_flags"]
        for field in array_fields:
            value = analysis.get(field, [])
            assert isinstance(value, list), f"{field} should be a list, got {type(value)}"
            print(f"  [OK] {field} is a list with {len(value)} items")
        
        print("\n[PASS] All validations passed!")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pipeline_with_rent_roll():
    """Test pipeline with a mock rent roll."""
    print("\n" + "="*60)
    print("TEST 2: Pipeline with mock rent roll")
    print("="*60)
    
    pipeline = CREPipeline()
    
    # Simulate rent roll data
    mock_rent_roll = """
    RENT ROLL - 5041 BAYOU BOULEVARD
    As of: April 1, 2026
    
    | Suite | Tenant Name      | RSF    | Lease Start | Lease End   | Monthly Rent | Annual Rent | Rent PSF |
    |-------|------------------|--------|-------------|-------------|--------------|-------------|----------|
    | 100   | Acme Corp        | 12,500 | 01/01/2023  | 12/31/2028  | $15,625      | $187,500    | $15.00   |
    | 200   | Beta Industries  | 8,200  | 06/01/2022  | 05/31/2027  | $11,070      | $132,840    | $16.20   |
    | 300   | Gamma Tech       | 5,800  | 03/01/2024  | 02/28/2029  | $7,540       | $90,480     | $15.60   |
    | 400   | Delta Services   | 3,500  | 09/01/2023  | 08/31/2026  | $4,375       | $52,500     | $15.00   |
    | 500   | VACANT           | 2,000  | -           | -           | -            | -           | -        |
    
    TOTALS:
    - Total Building RSF: 32,000
    - Occupied RSF: 30,000
    - Vacant RSF: 2,000
    - Occupancy: 93.75%
    - Total Annual Rent: $463,320
    - Average Rent PSF: $15.44
    """
    
    files = [{
        "filename": "rent_roll_april_2026.pdf",
        "content": mock_rent_roll.encode('utf-8'),
        "content_type": "application/pdf",
    }]
    
    try:
        result = await pipeline.analyze(files, deal_name="Test Deal - Rent Roll")
        
        print("\n[SUCCESS] Pipeline completed!")
        print(f"\n--- Summary ---")
        print(f"Success: {result.get('success')}")
        
        if result.get("success"):
            analysis = result["analysis"]
            print(f"Deal Score: {analysis.get('overall_score')}")
            print(f"Tier: {analysis.get('tier')}")
            print(f"Tenants found: {len(analysis.get('tenants', []))}")
            print(f"Red flags: {len(analysis.get('red_flags', []))}")
            
            # Validate tenants is a list
            tenants = analysis.get("tenants", [])
            assert isinstance(tenants, list), f"tenants should be list, got {type(tenants)}"
            print(f"\n[PASS] Tenants is correctly a list")
            
        return result.get("success", False)
        
    except Exception as e:
        print(f"\n[FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_pipeline_multiple_docs():
    """Test pipeline with multiple documents."""
    print("\n" + "="*60)
    print("TEST 3: Pipeline with multiple documents")
    print("="*60)
    
    pipeline = CREPipeline()
    
    lease_content = """
    LEASE AGREEMENT
    Tenant: Acme Corp
    Suite: 100
    RSF: 12,500
    Annual Rent: $187,500
    Lease End: 12/31/2028
    """
    
    boma_content = """
    BOMA MEASUREMENT CERTIFICATE
    Property: 5041 Bayou Boulevard
    Measurement Standard: BOMA 2017
    
    Suite 100: 12,750 RSF (Acme Corp)
    Suite 200: 8,400 RSF (Beta Industries)
    Suite 300: 5,900 RSF (Gamma Tech)
    
    Total Building RSF: 32,500
    """
    
    files = [
        {
            "filename": "lease_acme.pdf",
            "content": lease_content.encode('utf-8'),
            "content_type": "application/pdf",
        },
        {
            "filename": "boma_certificate.pdf",
            "content": boma_content.encode('utf-8'),
            "content_type": "application/pdf",
        }
    ]
    
    try:
        result = await pipeline.analyze(files, deal_name="Test Deal - Multi Doc")
        
        print("\n[SUCCESS] Pipeline completed!")
        print(f"Documents processed: {result.get('analysis', {}).get('documents_processed', 0)}")
        
        # Check for RSF discrepancy detection
        analysis = result.get("analysis", {})
        rsf = analysis.get("rsf_reconciliation", {})
        if rsf:
            print(f"\nRSF Reconciliation:")
            print(f"  Rent Roll RSF: {rsf.get('rent_roll_rsf')}")
            print(f"  BOMA RSF: {rsf.get('boma_rsf')}")
            print(f"  Discrepancy: {rsf.get('discrepancy_sf')} SF")
        
        return result.get("success", False)
        
    except Exception as e:
        print(f"\n[FAIL] Pipeline error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_normalize_to_list():
    """Test the _normalize_to_list helper function."""
    print("\n" + "="*60)
    print("TEST 4: _normalize_to_list helper")
    print("="*60)
    
    pipeline = CREPipeline()
    
    test_cases = [
        (None, [], "None should return empty list"),
        ([], [], "Empty list should return empty list"),
        ([1, 2, 3], [1, 2, 3], "List should return same list"),
        ({"a": 1, "b": 2}, [1, 2], "Dict should return values as list"),
        ({"tenants": [1, 2]}, [1, 2], "Dict with tenants key should extract"),
        ("single", ["single"], "Single value should wrap in list"),
    ]
    
    all_passed = True
    for input_val, expected_type_check, description in test_cases:
        result = pipeline._normalize_to_list(input_val)
        is_list = isinstance(result, list)
        status = "[PASS]" if is_list else "[FAIL]"
        print(f"  {status} {description}: {type(result).__name__}")
        if not is_list:
            all_passed = False
    
    return all_passed


async def run_all_tests():
    """Run all e2e tests."""
    print("\n" + "#"*60)
    print("# CRE Document Intelligence - E2E Test Suite")
    print("#"*60)
    
    # Check for API key
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("\n[WARNING] OPENROUTER_API_KEY not set!")
        print("Tests requiring AI calls will fail.")
        print("Set the environment variable and re-run.")
    else:
        print(f"\n[OK] OPENROUTER_API_KEY is set (length: {len(api_key)})")
    
    results = {}
    
    # Run tests
    results["normalize_to_list"] = await test_normalize_to_list()
    
    if api_key:
        results["mock_pdf"] = await test_pipeline_with_mock_pdf()
        results["rent_roll"] = await test_pipeline_with_rent_roll()
        results["multi_doc"] = await test_pipeline_multiple_docs()
    else:
        print("\n[SKIP] Skipping AI tests (no API key)")
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {test_name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return all(results.values())


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
