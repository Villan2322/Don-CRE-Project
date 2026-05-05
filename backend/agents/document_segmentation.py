"""
Document Segmentation Agent

Analyzes multi-page PDFs to identify distinct document sections and split them
for independent processing. This handles the common case of management reports
that bundle multiple document types (rent roll, AR aging, disbursements, etc.)
into a single PDF.
"""

import re
from dataclasses import dataclass
from typing import Optional

try:
    from .base import BaseAgent
except ImportError:
    from agents.base import BaseAgent


@dataclass
class DocumentSegment:
    """A logical segment within a larger document."""
    segment_id: str
    doc_type: str
    start_page: int
    end_page: int
    title: str
    text: str
    confidence: float


# Pattern priority: Higher priority patterns are checked first within each page
# COVER_LETTER should only be detected on first page and requires specific signatures
SEGMENT_PATTERNS = {
    "RENT_ROLL": [
        # Actual rent roll table headers (more specific than just "collection report")
        r"tenant\s+name\s+.*\s+rent\s+.*\s+(paid|balance)",
        r"(plaza\s+building|strip\s+center).*tenant\s+name",
        r"sales\s+tax\s+rent\s+minimum\s+percentage",
        r"minimum\s+rent\s+percentage\s+rent\s+common",
        r"report\s+as\s+of.*tenant\s+name",
    ],
    "DISBURSEMENTS": [
        r"cash\s+receipts?\s+(and|&)\s+disbursements?",
        r"check\s+register",
        r"total\s+disbursements",
        r"cash\s+ending\s+balance",
        r"date\s+vendor\s+.*amount",
    ],
    "ENDING_RECEIVABLES": [
        r"ending\s+receivables\s+as\s+of",
        r"receivables\s+as\s+of",
        r"ending\s+receivables",
    ],
    "INCOME_EXPENSE": [
        r"income\s+(and|&)\s+expense\s+summary",
        r"operating\s+statement",
        r"net\s+operating\s+income",
        r"total\s+income.*total\s+expenses",
    ],
    "LEASE_RECAP": [
        r"lease\s+recap",
        r"lease\s+abstract",
        r"commencement.*expiration.*base\s+rent",
        r"tenant\s+.*suite\s+.*sf\s+.*term",
    ],
    "SALES_VOLUME": [
        r"sales\s+volume\s+report",
        r"gross\s+sales",
        r"monthly\s+sales.*ytd\s+sales",
    ],
    "COVER_LETTER": [
        # Cover letter must have greeting AND signature - very specific
        r"dear\s+\w+:.*very\s+truly\s+yours",
        r"dear\s+\w+:.*sincerely",
        r"enclosed\s+is.*monthly\s+report.*dear",
    ],
}


class DocumentSegmentationAgent(BaseAgent):
    """
    Segments multi-page documents into logical sections for independent processing.
    
    This agent:
    1. Analyzes text patterns to identify section boundaries
    2. Classifies each section by document type
    3. Returns structured segments for parallel extraction
    """
    
    def __init__(self):
        super().__init__(
            name="DocumentSegmentationAgent",
            system_prompt="""You are a document segmentation expert for commercial real estate documents.
            
Your task is to identify distinct sections within a multi-page document and classify each section.

Common document types found in CRE management reports:
- COVER_LETTER: Introductory letter summarizing the report
- RENT_ROLL: Tenant payment status with rent, CAM, taxes columns
- DISBURSEMENTS: Check register / cash disbursements
- ENDING_RECEIVABLES: AR aging / outstanding balances by tenant
- INCOME_EXPENSE: Operating statement / P&L
- LEASE_RECAP: Summary of lease terms
- SALES_VOLUME: Tenant sales reporting

Return JSON with segments array, each containing:
- doc_type: The document type
- start_marker: Text that marks the start of this section
- end_marker: Text that marks the end (or start of next section)
- confidence: 0-1 confidence score
"""
        )
    
    def segment_by_patterns(self, text: str, page_texts: list[str]) -> list[DocumentSegment]:
        """
        Use regex patterns to identify document segments.
        Improved to handle:
        1. Cover letters that mention multiple section types
        2. Tabular data without explicit headers (rent rolls)
        3. Multi-section pages
        """
        segments = []
        
        # First, check if first page is a cover letter (has greeting + signature)
        first_page_lower = page_texts[0].lower() if page_texts else ""
        is_cover_letter = (
            ("dear " in first_page_lower or "enclosed" in first_page_lower) and 
            ("truly yours" in first_page_lower or "sincerely" in first_page_lower)
        )
        
        if is_cover_letter:
            # Cover letter is ONLY the first page
            segments.append(DocumentSegment(
                segment_id="seg-1",
                doc_type="COVER_LETTER",
                start_page=1,
                end_page=1,
                title="Cover Letter",
                text=page_texts[0],
                confidence=0.9,
            ))
            # Continue processing from page 2
            remaining_pages = page_texts[1:] if len(page_texts) > 1 else []
            page_offset = 1
        else:
            remaining_pages = page_texts
            page_offset = 0
        
        # Now classify remaining pages by content, not by header mentions
        current_type: Optional[str] = None
        current_start: int = 0
        current_confidence: float = 0
        current_text: list[str] = []
        
        for page_idx, page_text in enumerate(remaining_pages):
            page_lower = page_text.lower()
            detected_type = None
            best_confidence = 0
            
            # Check for specific section markers (not just mentions)
            # RENT_ROLL: Look for actual tenant data tables
            if re.search(r'(plaza\s+building|strip|tenant\s+name).*\n.*\d+\.\d{2}', page_lower, re.DOTALL):
                detected_type = "RENT_ROLL"
                best_confidence = 0.85
            elif re.search(r'sales\s+tax\s+rent\s+(minimum|percentage)', page_lower):
                detected_type = "RENT_ROLL"
                best_confidence = 0.85
            elif re.search(r'(minimum|percentage)\s+.*common.*area\s+maint', page_lower):
                detected_type = "RENT_ROLL"
                best_confidence = 0.8
            
            # DISBURSEMENTS: Check register or cash disbursements
            if not detected_type and re.search(r'(check\s+register|total\s+disbursements|cash\s+ending)', page_lower):
                detected_type = "DISBURSEMENTS"
                best_confidence = 0.85
            
            # ENDING_RECEIVABLES: AR aging
            if not detected_type and re.search(r'ending\s+receivables\s+(as\s+of|report)', page_lower):
                detected_type = "ENDING_RECEIVABLES"
                best_confidence = 0.85
            
            # LEASE_RECAP
            if not detected_type and re.search(r'lease\s+recap|commencement.*expiration', page_lower):
                detected_type = "LEASE_RECAP"
                best_confidence = 0.85
            
            # SALES_VOLUME
            if not detected_type and re.search(r'sales\s+volume\s+report|gross\s+sales', page_lower):
                detected_type = "SALES_VOLUME"
                best_confidence = 0.85
            
            # INCOME_EXPENSE
            if not detected_type and re.search(r'income\s+(and|&)\s+expense|operating\s+statement', page_lower):
                detected_type = "INCOME_EXPENSE"
                best_confidence = 0.85
            
            # If no specific detection, check for tabular data patterns
            if not detected_type:
                # Count numeric values and columns - sign of tabular data
                numbers = re.findall(r'\d+\.\d{2}', page_text)
                if len(numbers) > 10:
                    # Lots of decimal numbers suggests financial table
                    # Check if previous type was a table type
                    if current_type in ["RENT_ROLL", "ENDING_RECEIVABLES"]:
                        detected_type = current_type
                        best_confidence = 0.7
                    else:
                        detected_type = "RENT_ROLL"  # Default to rent roll for tabular data
                        best_confidence = 0.6
            
            # Handle type changes
            if detected_type and detected_type != current_type:
                # Save previous segment
                if current_type and current_text:
                    segments.append(DocumentSegment(
                        segment_id=f"seg-{len(segments)+1}",
                        doc_type=current_type,
                        start_page=current_start + page_offset + 1,
                        end_page=page_idx + page_offset,
                        title=self._extract_title(current_text[0]),
                        text="\n".join(current_text),
                        confidence=current_confidence,
                    ))
                
                # Start new segment
                current_type = detected_type
                current_start = page_idx
                current_confidence = best_confidence
                current_text = [page_text]
            elif detected_type:
                # Continue current segment
                current_text.append(page_text)
                current_confidence = max(current_confidence, best_confidence)
            else:
                # No detection - add to current segment if exists
                if current_type:
                    current_text.append(page_text)
        
        # Save final segment
        if current_type and current_text:
            segments.append(DocumentSegment(
                segment_id=f"seg-{len(segments)+1}",
                doc_type=current_type,
                start_page=current_start + page_offset + 1,
                end_page=len(page_texts),
                title=self._extract_title(current_text[0]),
                text="\n".join(current_text),
                confidence=current_confidence,
            ))
        
        # If no segments found, treat entire document as unknown
        if not segments:
            segments.append(DocumentSegment(
                segment_id="seg-1",
                doc_type="UNKNOWN",
                start_page=1,
                end_page=len(page_texts),
                title="Full Document",
                text=text,
                confidence=0.5,
            ))
        
        return segments
    
    def _extract_title(self, text: str) -> str:
        """Extract a title from the first few lines of text."""
        lines = [l.strip() for l in text.split("\n") if l.strip()][:5]
        for line in lines:
            # Skip short lines and lines that look like headers
            if len(line) > 10 and not line.startswith("Page"):
                return line[:100]
        return "Untitled Section"
    
    async def segment_with_llm(self, text: str, page_texts: list[str]) -> list[DocumentSegment]:
        """
        Use LLM to identify document segments when patterns are ambiguous.
        
        Args:
            text: Full document text (first 10000 chars for context)
            page_texts: List of text per page
            
        Returns:
            List of identified segments
        """
        # First try pattern-based segmentation
        pattern_segments = self.segment_by_patterns(text, page_texts)
        
        # If we got good results, use them
        if len(pattern_segments) > 1 or (pattern_segments and pattern_segments[0].confidence > 0.7):
            return pattern_segments
        
        # Otherwise, use LLM for more nuanced analysis
        truncated_text = text[:15000] if len(text) > 15000 else text
        
        prompt = f"""Analyze this document and identify distinct sections.

Document text (truncated):
{truncated_text}

Total pages: {len(page_texts)}

Identify each logical section with:
1. doc_type (RENT_ROLL, DISBURSEMENTS, ENDING_RECEIVABLES, INCOME_EXPENSE, LEASE_RECAP, SALES_VOLUME, COVER_LETTER, or UNKNOWN)
2. start_page (1-indexed)
3. end_page (1-indexed, inclusive)
4. title (brief description)
5. confidence (0-1)

Return JSON array of segments."""

        try:
            response = await self.call_llm(self.system_prompt, prompt, max_tokens=2000)
            parsed = self._extract_json(response)
            
            if isinstance(parsed, list):
                segments = []
                for item in parsed:
                    start_page = item.get("start_page", 1)
                    end_page = item.get("end_page", len(page_texts))
                    
                    # Gather text for this segment
                    segment_text = "\n".join(
                        page_texts[i] for i in range(start_page - 1, min(end_page, len(page_texts)))
                    )
                    
                    segments.append(DocumentSegment(
                        segment_id=f"seg-{len(segments)+1}",
                        doc_type=item.get("doc_type", "UNKNOWN"),
                        start_page=start_page,
                        end_page=end_page,
                        title=item.get("title", "Untitled"),
                        text=segment_text,
                        confidence=item.get("confidence", 0.5),
                    ))
                
                return segments if segments else pattern_segments
            
        except Exception as e:
            print(f"LLM segmentation failed: {e}")
        
        return pattern_segments
    
    async def segment_document(
        self, 
        full_text: str, 
        page_texts: Optional[list[str]] = None
    ) -> list[DocumentSegment]:
        """
        Main entry point for document segmentation.
        
        Args:
            full_text: Complete document text
            page_texts: Optional list of text per page (for better segmentation)
            
        Returns:
            List of DocumentSegment objects
        """
        # If no page texts provided, split by common page markers
        if not page_texts:
            # Try various page marker patterns
            page_patterns = [
                r'(?=-{3,}\s*Page\s*\d+\s*-{3,})',  # --- Page 1 ---
                r'(?=Page:\s*\d+)',                   # Page: 1
                r'(?=\n\s*Page\s+\d+\s*\n)',         # Page 1 on its own line
                r'(?=\[Page\s*\d+\])',               # [Page 1]
            ]
            
            page_texts = None
            for pattern in page_patterns:
                parts = re.split(pattern, full_text)
                if len(parts) > 1:
                    page_texts = [p for p in parts if p.strip()]
                    break
            
            # If no pattern matched, treat as single page
            if not page_texts or len(page_texts) <= 1:
                page_texts = [full_text]
        
        # Use pattern matching first, then LLM if needed
        return await self.segment_with_llm(full_text, page_texts)
