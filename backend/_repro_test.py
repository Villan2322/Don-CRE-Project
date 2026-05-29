import sys, os, traceback, asyncio
# Disable LangSmith tracing for local test to avoid 401 noise
pass

# Build a realistic rent roll CSV
csv_content = b"""Suite,Tenant,RSF,Monthly Rent,Lease Start,Lease End
101,American Eagle Shirts & More,2500,4500,2022-01-01,2027-12-31
102,Top Fashion,1800,3200,2021-06-01,2026-05-31
103,Beauty Town,1200,2100,2023-03-01,2028-02-28
104,Rainbow #818,3000,5200,2020-09-01,2025-08-31
105,Citi Trends #271,4500,7800,2019-01-01,2029-12-31
"""

try:
    from graph import graph
    print("[repro] graph imported OK")
except Exception as e:
    print("[repro] IMPORT FAILED:")
    traceback.print_exc()
    sys.exit(1)

deal_id = "test-deal-1"
initial_state = {
    "deal_id": deal_id, "deal_name": "Town and Country Plaza",
    "raw_files": {"rent_roll.csv": csv_content},
    "file_content_types": {"rent_roll.csv": "text/csv"},
    "raw_documents": [], "ingest_errors": [],
    "classified_documents": [], "classification_errors": [],
    "extractions": [], "extraction_errors": [],
    "synthesis": {}, "rsf_recovery": {}, "score_summary": {},
    "synthesis_error": None, "arithmetic_verification": {},
    "rent_roll_analysis": {}, "rsf_reconciliation": {},
    "red_flags_result": {}, "deal_score_result": {},
    "completeness_result": {}, "pipeline_stage": "pending",
    "pipeline_errors": [], "completed_at": None,
}

try:
    result = asyncio.run(graph.ainvoke(initial_state))
    print("[repro] PIPELINE OK")
    print("[repro] pipeline_stage:", result.get("pipeline_stage"))
    print("[repro] pipeline_errors:", result.get("pipeline_errors"))
    print("[repro] score_summary:", result.get("score_summary"))
    print("[repro] extractions count:", len(result.get("extractions", [])))
    print("[repro] rent_roll_analysis keys:", list(result.get("rent_roll_analysis", {}).keys()))
    print("\n[repro] === raw_documents ===")
    for d in result.get("raw_documents", []):
        print("  file:", d["filename"], "| file_type:", d.get("file_type"), "| text_len:", len(d.get("extracted_text","")))
        print("  text preview:", repr(d.get("extracted_text","")[:200]))
    print("\n[repro] === classified_documents ===")
    for d in result.get("classified_documents", []):
        print("  file:", d["filename"], "| doc_type:", d.get("doc_type"), "| conf:", d.get("classification_confidence"), "| reason:", d.get("classification_reasoning"))
    print("\n[repro] ingest_errors:", result.get("ingest_errors"))
    print("[repro] classification_errors:", result.get("classification_errors"))
except Exception as e:
    print("[repro] PIPELINE CRASHED:")
    traceback.print_exc()
    sys.exit(1)
