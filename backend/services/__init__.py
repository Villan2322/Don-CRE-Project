try:
    from .document_processor import processor, DocumentProcessor
except ImportError:
    from document_processor import processor, DocumentProcessor

__all__ = ["processor", "DocumentProcessor"]
