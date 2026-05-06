"""
OCR Agent
Handles optical character recognition for scanned documents and images.
Uses Claude Vision as primary OCR (works in serverless), falls back to Tesseract if available.
"""

import base64
import io
import os
from typing import Optional

try:
    import anthropic
    HAS_CLAUDE = True
except ImportError:
    HAS_CLAUDE = False

try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_bytes
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


class OCRAgent:
    """Agent for OCR processing of scanned documents using Claude Vision."""
    
    def __init__(self):
        self.name = "OCRAgent"
        self.min_confidence = 70.0
        self.client = None
        if HAS_CLAUDE and os.environ.get("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic()
    
    async def process(
        self,
        file_content: bytes,
        filename: str,
        page_count: Optional[int] = None
    ) -> dict:
        """
        Process a document with OCR using Claude Vision (primary) or Tesseract (fallback).
        """
        filename_lower = filename.lower()
        
        # Try Claude Vision first (works in serverless)
        if self.client:
            try:
                if filename_lower.endswith('.pdf'):
                    return await self._ocr_pdf_with_claude(file_content, page_count)
                elif filename_lower.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                    return await self._ocr_image_with_claude(file_content, filename)
            except Exception as e:
                print(f"[OCR] Claude Vision failed: {e}, trying fallback...")
        
        # Fallback to Tesseract if available
        if HAS_TESSERACT:
            try:
                if filename_lower.endswith('.pdf'):
                    return await self._ocr_pdf(file_content, page_count)
                elif filename_lower.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                    return await self._ocr_image(file_content)
            except Exception as e:
                print(f"[OCR] Tesseract failed: {e}")
        
        return {
            "document_readable": False,
            "cleaned_text": "",
            "confidence": 0.0,
            "ocr_issues_found": ["No OCR method available (Claude API or Tesseract)"],
            "pages_processed": 0
        }
    
    async def _ocr_pdf_with_claude(self, file_content: bytes, page_count: Optional[int] = None) -> dict:
        """OCR a PDF using Claude's native PDF support."""
        # Claude can process PDFs directly via base64
        pdf_base64 = base64.standard_b64encode(file_content).decode("utf-8")
        
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": """Extract ALL text from this document exactly as it appears. 
This is a commercial real estate document that may contain:
- Rent rolls with tenant names, suite numbers, square footage, rent amounts
- Lease terms, dates, escalation clauses
- Financial data, receivables, disbursements
- Property information

Preserve the structure including tables, columns, and formatting.
Do NOT summarize - extract the complete text verbatim.
If there are tables, format them with tabs or pipes to preserve column alignment."""
                    }
                ],
            }],
        )
        
        extracted_text = message.content[0].text
        
        return {
            "document_readable": len(extracted_text) > 100,
            "cleaned_text": extracted_text,
            "confidence": 95.0,  # Claude Vision is highly accurate
            "ocr_issues_found": [],
            "pages_processed": page_count or 1
        }
    
    async def _ocr_image_with_claude(self, file_content: bytes, filename: str) -> dict:
        """OCR an image using Claude Vision."""
        # Determine media type
        ext = filename.lower().split('.')[-1]
        media_type_map = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        media_type = media_type_map.get(ext, 'image/png')
        
        image_base64 = base64.standard_b64encode(file_content).decode("utf-8")
        
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Extract ALL text from this image exactly as it appears. Preserve structure and formatting."
                    }
                ],
            }],
        )
        
        extracted_text = message.content[0].text
        
        return {
            "document_readable": len(extracted_text) > 20,
            "cleaned_text": extracted_text,
            "confidence": 95.0,
            "ocr_issues_found": [],
            "pages_processed": 1
        }
    
    async def _ocr_pdf(self, file_content: bytes, page_count: Optional[int] = None) -> dict:
        """OCR a PDF document by converting pages to images."""
        try:
            # Convert PDF pages to images
            images = convert_from_bytes(file_content, dpi=300)
            
            text_parts = []
            confidences = []
            issues = []
            
            for i, image in enumerate(images):
                # Get OCR data with confidence
                ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
                
                # Extract text and calculate confidence
                page_text = pytesseract.image_to_string(image)
                text_parts.append(f"=== Page {i + 1} ===\n{page_text}")
                
                # Calculate average confidence for non-empty entries
                conf_values = [c for c, t in zip(ocr_data['conf'], ocr_data['text']) 
                              if t.strip() and c != -1]
                if conf_values:
                    avg_conf = sum(conf_values) / len(conf_values)
                    confidences.append(avg_conf)
                    
                    if avg_conf < self.min_confidence:
                        issues.append(f"Page {i + 1}: Low OCR confidence ({avg_conf:.1f}%)")
            
            # Calculate overall confidence
            overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            cleaned_text = "\n\n".join(text_parts)
            
            # Clean up common OCR artifacts
            cleaned_text = self._clean_ocr_text(cleaned_text)
            
            return {
                "document_readable": overall_confidence >= self.min_confidence and len(cleaned_text) > 50,
                "cleaned_text": cleaned_text,
                "confidence": overall_confidence,
                "ocr_issues_found": issues if issues else [],
                "pages_processed": len(images)
            }
            
        except Exception as e:
            return {
                "document_readable": False,
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": [f"PDF OCR failed: {str(e)}"],
                "pages_processed": 0
            }
    
    async def _ocr_image(self, file_content: bytes) -> dict:
        """OCR a single image."""
        try:
            image = Image.open(io.BytesIO(file_content))
            
            # Get OCR data with confidence
            ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            text = pytesseract.image_to_string(image)
            
            # Calculate confidence
            conf_values = [c for c, t in zip(ocr_data['conf'], ocr_data['text']) 
                          if t.strip() and c != -1]
            confidence = sum(conf_values) / len(conf_values) if conf_values else 0.0
            
            cleaned_text = self._clean_ocr_text(text)
            
            issues = []
            if confidence < self.min_confidence:
                issues.append(f"Low OCR confidence ({confidence:.1f}%)")
            
            return {
                "document_readable": confidence >= self.min_confidence and len(cleaned_text) > 20,
                "cleaned_text": cleaned_text,
                "confidence": confidence,
                "ocr_issues_found": issues,
                "pages_processed": 1
            }
            
        except Exception as e:
            return {
                "document_readable": False,
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": [f"Image OCR failed: {str(e)}"],
                "pages_processed": 0
            }
    
    def _clean_ocr_text(self, text: str) -> str:
        """Clean common OCR artifacts from extracted text."""
        # Remove excessive whitespace
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip lines that are mostly special characters (OCR noise)
            alphanumeric = sum(c.isalnum() for c in line)
            total = len(line.strip())
            
            if total == 0:
                cleaned_lines.append('')
            elif alphanumeric / total > 0.3:  # At least 30% alphanumeric
                cleaned_lines.append(line)
        
        # Remove excessive blank lines
        result = []
        blank_count = 0
        
        for line in cleaned_lines:
            if line.strip():
                result.append(line)
                blank_count = 0
            else:
                blank_count += 1
                if blank_count <= 2:  # Max 2 consecutive blank lines
                    result.append('')
        
        return '\n'.join(result).strip()
