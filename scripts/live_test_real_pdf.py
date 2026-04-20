"""
Live pipeline test using a real PDF generated with reportlab.
This tests the actual happy path that matches what users upload.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def build_pdf() -> bytes:
    """Build a real in-memory PDF with rent roll data."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        import io

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        elems = []

        elems.append(Paragraph("TOWN AND COUNTRY PLAZA - RENT ROLL", styles["Heading1"]))
        elems.append(Paragraph("February 2026", styles["Normal"]))
        elems.append(Spacer(1, 12))

        data = [
            ["Suite", "Tenant", "RSF", "Monthly Rent", "Annual Rent", "Lease Start", "Lease End"],
            ["101", "Publix Super Markets", "22,500", "$22,500", "$270,000", "01/01/2020", "12/31/2027"],
            ["102", "Starbucks Corp", "1,850", "$6,475", "$77,700", "03/01/2021", "02/28/2026"],
            ["103", "Great Clips", "1,200", "$3,600", "$43,200", "06/01/2019", "05/31/2027"],
            ["104", "Subway", "1,100", "$3,300", "$39,600", "09/01/2022", "08/31/2025"],
            ["105", "State Farm", "1,400", "$4,200", "$50,400", "01/01/2023", "12/31/2025"],
            ["106", "T-Mobile", "1,300", "$4,550", "$54,600", "04/01/2020", "03/31/2026"],
            ["107", "VACANT", "1,500", "$0", "$0", "", ""],
            ["108", "Supercuts", "900", "$2,700", "$32,400", "07/01/2021", "06/30/2026"],
            ["109", "H&R Block", "1,100", "$3,300", "$39,600", "01/01/2022", "12/31/2025"],
            ["110", "Pizza Hut", "1,200", "$3,600", "$43,200", "08/01/2020", "07/31/2026"],
            ["", "TOTAL OCCUPIED", "33,550", "$54,225", "$650,700", "", ""],
            ["", "TOTAL VACANT", "1,500", "", "", "", ""],
            ["", "TOTAL BUILDING SF", "35,050", "", "", "", ""],
        ]

        t = Table(data, colWidths=[40, 130, 60, 80, 80, 75, 75])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, -3), (-1, -1), colors.lightgrey),
            ("FONTNAME", (0, -3), (-1, -1), "Helvetica-Bold"),
        ]))
        elems.append(t)
        doc.build(elems)
        return buf.getvalue()
    except ImportError:
        # reportlab not installed - return minimal valid PDF bytes
        return b""


async def run():
    from services.pipeline import CREPipeline

    pdf_bytes = build_pdf()

    if not pdf_bytes:
        print("ERROR: reportlab not installed. Run: uv add reportlab")
        return

    print(f"Built real PDF: {len(pdf_bytes):,} bytes")

    files = [{
        "filename": "TownAndCountry_RentRoll_Feb2026.pdf",
        "content": pdf_bytes,
        "content_type": "application/pdf",
    }]

    # PA says 50,000 SF — rent roll shows 35,050 → 14,950 SF discrepancy
    property_appraiser_sf = 50000.0

    print("=" * 70)
    print(f"PA Baseline: {property_appraiser_sf:,.0f} SF")
    print(f"Rent Roll Total: 35,050 SF  (expected gap: 14,950 SF)")
    print("=" * 70)

    pipeline = CREPipeline()
    result = await pipeline.analyze(files, "Town And Country Plaza", property_appraiser_sf)

    print("\n--- TRACE LOG ---")
    for entry in result.get("trace_log", []):
        level = entry.get("level", "info").upper()
        print(f"  [{level:7}] [{entry.get('stage')}] {entry.get('message')}")

    print("\n--- RESULTS ---")
    print(f"  Score:           {result.get('score')}")
    print(f"  Tier:            {result.get('tier')}")
    print(f"  PA SF:           {result.get('property_appraiser_sf')}")
    print(f"  RSF Recovery SF: {result.get('rsf_recovery_sf')}")
    print(f"  RSF Recovery $:  ${result.get('rsf_recovery_annual_value', 0):,.0f}/yr")

    tenants = result.get("tenants", [])
    print(f"\n--- TENANTS ({len(tenants)}) ---")
    for t in (tenants or []):
        if not t:
            continue
        name = t.get("name") or t.get("tenant") or "?"
        rsf = t.get("rsf") or t.get("sf") or 0
        print(f"  {name:<35} {rsf:>7,.0f} SF")

    flags = result.get("red_flags", [])
    print(f"\n--- RED FLAGS ({len(flags)}) ---")
    for f in (flags or []):
        if not f:
            continue
        print(f"  [{f.get('severity')}] {f.get('flag') or f.get('description') or '?'}")
        if f.get("impact"):
            print(f"         {f.get('impact')}")

    print()


if __name__ == "__main__":
    asyncio.run(run())
