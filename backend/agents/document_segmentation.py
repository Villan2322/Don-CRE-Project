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


SEGMENT_PATTERNS = {
    "COVER_LETTER": [
        r"monthly\s+report",
        r"dear\s+\w+:",
        r"enclosed\s+is",
        r"very\s+truly\s+yours",
    ],
    "RENT_ROLL": [
        r"collection\s+report",
        r"tenant\s+name.*rent.*paid.*balance",
        r"minimum\s+rent.*percentage\s+rent",
        r"sales\s+tax.*rent.*common\s+area",
        r"unpaid.*balance",
    ],
    "DISBURSEMENTS": [
        r"cash\s+receipts?\s+(and|&)\s+disbursements?",
        r"check\s*#.*vendor.*amount",
        r"total\s+disbursements",
        r"cash\s+ending\s+balance",
    ],
    "ENDING_RECEIVABLES": [
        r"ending\s+receivables",
        r"receivables\s+as\s+of",
        r"tenant\s+name.*sales\s+tax.*rent.*total",
    ],
    "INCOME_EXPENSE": [
        r"income\s+(and|&)\s+expense",
        r"operating\s+statement",
        r"net\s+operating\s+income",
        r"total\s+income.*total\s+expenses",
    ],
    "LEASE_RECAP": [
        r"lease\s+recap",
        r"lease\s+abstract",
        r"commencement.*expiration.*rent",
        r"tenant.*suite.*sf.*term",
    ],
    "SALES_VOLUME": [
        r"sales\s+volume",
        r"gross\s+sales",
        r"monthly\s+sales.*ytd\s+sales",
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
        
        Args:
            text: Full document text
            page_texts: List of text per page
            
        Returns:
            List of identified segments
        """
        segments = []
        text_lower = text.lower()
        
        # Track which pages contain which document types
        page_types: dict[int, list[tuple[str, float]]] = {i: [] for i in range(len(page_texts))}
        
        for page_idx, page_text in enumerate(page_texts):
            page_lower = page_text.lower()
            
            for doc_type, patterns in SEGMENT_PATTERNS.items():
                matches = 0
                for pattern in patterns:
                    if re.search(pattern, page_lower):
                        matches += 1
                
                if matches > 0:
                    confidence = min(matches / len(patterns) * 1.5, 1.0)
                    page_types[page_idx].append((doc_type, confidence))
        
        # Consolidate consecutive pages of the same type
        current_type: Optional[str] = None
        current_start: int = 0
        current_confidence: float = 0
        current_text: list[str] = []
        
        for page_idx in range(len(page_texts)):
            page_matches = page_types[page_idx]
            
            if page_matches:
                # Get the highest confidence match for this page
                best_match = max(page_matches, key=lambda x: x[1])
                best_type, confidence = best_match
                
                if best_type != current_type:
                    # Save previous segment if exists
                    if current_type and current_text:
                        segments.append(DocumentSegment(
                            segment_id=f"seg-{len(segments)+1}",
                            doc_type=current_type,
                            start_page=current_start + 1,  # 1-indexed
                            end_page=page_idx,  # 1-indexed (exclusive)
                            title=self._extract_title(current_text[0]),
                            text="\n".join(current_text),
                            confidence=current_confidence,
                        ))
                    
                    # Start new segment
                    current_type = best_type
                    current_start = page_idx
                    current_confidence = confidence
                    current_text = [page_texts[page_idx]]
                else:
                    # Continue current segment
                    current_text.append(page_texts[page_idx])
                    current_confidence = max(current_confidence, confidence)
            else:
                # No clear match - continue previous segment if exists
                if current_type:
                    current_text.append(page_texts[page_idx])
        
        # Save final segment
        if current_type and current_text:
            segments.append(DocumentSegment(
                segment_id=f"seg-{len(segments)+1}",
                doc_type=current_type,
                start_page=current_start + 1,
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
            # Try to split by "Page: X" markers
            page_pattern = r'(?=Page:\s*\d+)'
            parts = re.split(page_pattern, full_text)
            page_texts = [p for p in parts if p.strip()]
            
            # If that didn't work, treat as single page
            if len(page_texts) <= 1:
                page_texts = [full_text]
        
        # Use pattern matching first, then LLM if needed
        return await self.segment_with_llm(full_text, page_texts)
