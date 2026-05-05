"""
OCR Agent
Handles optical character recognition for scanned documents and images.
"""

import io
from typing import Optional

try:
    import pytesseract
    from PIL import Image
    from pdf2image import convert_from_bytes
    HAS_OCR = True
except ImportError:
    HAS_OCR = False


class OCRAgent:
    """Agent for OCR processing of scanned documents."""
    
    def __init__(self):
        self.name = "OCRAgent"
        self.min_confidence = 70.0  # Minimum OCR confidence threshold
    
    async def process(
        self,
        file_content: bytes,
        filename: str,
        page_count: Optional[int] = None
    ) -> dict:
        """
        Process a document with OCR.
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            page_count: Expected page count (for PDFs)
            
        Returns:
            dict with extracted text, confidence, and any issues found
        """
        if not HAS_OCR:
            return {
                "document_readable": False,
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": ["OCR libraries not installed (pytesseract, PIL, pdf2image)"],
                "pages_processed": 0
            }
        
        filename_lower = filename.lower()
        
        try:
            # Handle PDFs
            if filename_lower.endswith('.pdf'):
                return await self._ocr_pdf(file_content, page_count)
            
            # Handle images
            if filename_lower.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                return await self._ocr_image(file_content)
            
            return {
                "document_readable": False,
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": [f"Unsupported file type for OCR: {filename}"],
                "pages_processed": 0
            }
            
        except Exception as e:
            return {
                "document_readable": False,
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": [f"OCR processing error: {str(e)}"],
                "pages_processed": 0
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
