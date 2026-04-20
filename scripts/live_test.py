"""
Live pipeline test - runs the full pipeline and prints every trace step.
Simulates a realistic rent roll so we can see exactly what the AI extracts.
"""

import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

async def run():
    from services.pipeline import CREPipeline

    # Realistic rent roll text - matches what an actual PDF rent roll looks like
    rent_roll_text = """
TOWN AND COUNTRY PLAZA
RENT ROLL - February 2026
Property Appraiser Parcel: 08-2220-000-0010

TENANT ROSTER

Suite  Tenant Name                     RSF     Base Rent/Mo   Annual Rent   Lease Start  Lease End    Exp Type
---    ---                             ---     ---            ---           ---          ---          ---
101    Publix Super Markets Inc        22,500  $22,500.00     $270,000.00   01/01/2020   12/31/2027   NNN
102    Starbucks Corporation           1,850   $6,475.00      $77,700.00    03/01/2021   02/28/2026   NNN
103    Great Clips Inc                 1,200   $3,600.00      $43,200.00    06/01/2019   05/31/2027   NNN
104    Subway Restaurants              1,100   $3,300.00      $39,600.00    09/01/2022   08/31/2025   NNN
105    State Farm Insurance            1,400   $4,200.00      $50,400.00    01/01/2023   12/31/2025   Gross
106    T-Mobile USA Inc                1,300   $4,550.00      $54,600.00    04/01/2020   03/31/2026   NNN
107    VACANT                          1,500   $0.00          $0.00
108    Supercuts                       900     $2,700.00      $32,400.00    07/01/2021   06/30/2026   NNN
109    H&R Block                       1,100   $3,300.00      $39,600.00    01/01/2022   12/31/2025   NNN
110    Pizza Hut                       1,200   $3,600.00      $43,200.00    08/01/2020   07/31/2026   NNN

SUMMARY
Total Occupied SF:    33,550
Total Vacant SF:       1,500
Total Building SF:    35,050
Occupancy Rate:       95.7%
Total Monthly Rent:   $54,225.00
Total Annual Rent:    $650,700.00
"""

    # Encode as bytes (simulating a PDF upload)
    doc_bytes = rent_roll_text.encode('utf-8')

    files = [
        {
            "filename": "Town_Country_Plaza_RentRoll_Feb2026.pdf",
            "content": doc_bytes,
            "content_type": "application/pdf",
        }
    ]

    property_appraiser_sf = 50000.0  # 50,000 SF official - rent roll shows 35,050 → 14,950 SF gap

    print("=" * 70)
    print("LIVE PIPELINE TEST")
    print(f"Document: {files[0]['filename']}")
    print(f"PA Baseline: {property_appraiser_sf:,.0f} SF")
    print("=" * 70)

    pipeline = CREPipeline()

    try:
        result = await pipeline.analyze(files, "Town And Country Plaza", property_appraiser_sf)
    except Exception as e:
        import traceback
        print(f"\nPIPELINE CRASHED: {e}")
        traceback.print_exc()
        return

    print("\n--- TRACE LOG ---")
    for entry in result.get("trace_log", []):
        level = entry.get("level", "info").upper()
        stage = entry.get("stage", "?")
        msg = entry.get("message", "")
        print(f"  [{level:7}] [{stage}] {msg}")

    print("\n--- TOP-LEVEL RESULTS ---")
    print(f"  Success:           {result.get('success')}")
    print(f"  Score:             {result.get('score')}")
    print(f"  Tier:              {result.get('tier')}")
    print(f"  Docs Processed:    {result.get('documents_processed')}")
    print(f"  PA SF:             {result.get('property_appraiser_sf')}")
    print(f"  RSF Recovery SF:   {result.get('rsf_recovery_sf')}")
    print(f"  RSF Recovery $:    ${result.get('rsf_recovery_annual_value', 0):,.0f}")

    tenants = result.get("tenants", [])
    print(f"\n--- TENANTS ({len(tenants)}) ---")
    for t in tenants:
        if t is None:
            print("  [null tenant — SHOULD BE FILTERED]")
            continue
        name = t.get("name") or t.get("tenant") or t.get("tenant_name") or "?"
        rsf = t.get("rsf") or t.get("sf") or 0
        rent = t.get("annual_rent") or 0
        print(f"  {name:<35} {rsf:>7,.0f} SF   ${rent:>10,.0f}/yr")

    red_flags = result.get("red_flags", [])
    print(f"\n--- RED FLAGS ({len(red_flags)}) ---")
    for f in red_flags:
        if f is None:
            print("  [null flag — SHOULD BE FILTERED]")
            continue
        sev = f.get("severity", "?")
        flag = f.get("flag") or f.get("description") or f.get("message") or "?"
        impact = f.get("impact", "")
        print(f"  [{sev}] {flag}")
        if impact:
            print(f"         Impact: {impact}")

    what_next = result.get("what_to_get_next", [])
    print(f"\n--- WHAT TO GET NEXT ({len(what_next)}) ---")
    for item in what_next:
        if item is None:
            continue
        if isinstance(item, str):
            print(f"  - {item}")
        else:
            print(f"  - {item.get('document', item)}")

    rsf = result.get("rsf_analysis", {})
    print(f"\n--- RSF ANALYSIS ---")
    print(json.dumps(rsf, indent=2, default=str))

    if result.get("error"):
        print(f"\nERROR: {result['error']}")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
