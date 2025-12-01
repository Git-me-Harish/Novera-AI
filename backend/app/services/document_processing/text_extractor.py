"""
Text extraction service using Unstructured.io and PyMuPDF.
Handles PDF, DOCX, TXT, and XLSX files with intelligent layout detection.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import fitz  # PyMuPDF
import PyPDF2
from docx import Document as DocxDocument
import openpyxl
from unstructured.documents.elements import (
    Title, NarrativeText, ListItem, Table, Image, Header, Footer
)
from loguru import logger


@dataclass
class ExtractedElement:
    """Represents a single extracted element from a document."""
    content: str
    element_type: str  # 'text', 'table', 'title', 'header', 'footer', 'list'
    page_number: int
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.content,
            'element_type': self.element_type,
            'page_number': self.page_number,
            'metadata': self.metadata
        }


@dataclass
class DocumentStructure:
    """Represents the complete structure of an extracted document."""
    elements: List[ExtractedElement]
    total_pages: int
    has_tables: bool
    has_images: bool
    metadata: Dict[str, Any]
    
    def get_elements_by_type(self, element_type: str) -> List[ExtractedElement]:
        """Filter elements by type."""
        return [e for e in self.elements if e.element_type == element_type]
    
    def get_elements_by_page(self, page_num: int) -> List[ExtractedElement]:
        """Filter elements by page number."""
        return [e for e in self.elements if e.page_number == page_num]


class TextExtractor:
    """
    Intelligent text extraction with layout awareness.
    Uses Unstructured.io for structured extraction and PyMuPDF as fallback.
    """
    
    def __init__(self):
        self.supported_formats = {'.pdf', '.docx', '.doc', '.txt', '.xlsx', '.xls'}
    
    def extract_document(self, file_path: Path) -> DocumentStructure:
        """
        Extract structured content from document.
        
        Args:
            file_path: Path to document file
            
        Returns:
            DocumentStructure with all extracted elements
        """
        file_ext = file_path.suffix.lower()
        
        if file_ext not in self.supported_formats:
            raise ValueError(f"Unsupported file format: {file_ext}")
        
        logger.info(f"Extracting document: {file_path.name}")
        
        try:
            # Primary: Use Unstructured.io
            return self._extract_with_unstructured(file_path)
        except Exception as e:
            logger.warning(f"Unstructured.io extraction failed: {str(e)}")
            
            # Fallback: Use PyMuPDF for PDFs
            if file_ext == '.pdf':
                logger.info("Falling back to PyMuPDF extraction")
                return self._extract_with_pymupdf(file_path)
            else:
                raise Exception(f"Failed to extract document: {str(e)}")
    
    def _extract_with_unstructured(self, file_path: Path) -> DocumentStructure:
        """
        Extract using Unstructured.io library.
        Provides best layout understanding and structure preservation.
        """
        # Partition document into elements
        elements = partition(
            filename=str(file_path),
            strategy="hi_res",  # High resolution for better accuracy
            include_page_breaks=True,
            infer_table_structure=True,
            languages=["eng"],
        )
        
        extracted_elements = []
        has_tables = False
        has_images = False
        total_pages = 0
        
        for element in elements:
            # Determine element type
            if isinstance(element, Title):
                elem_type = "title"
            elif isinstance(element, Table):
                elem_type = "table"
                has_tables = True
            elif isinstance(element, ListItem):
                elem_type = "list"
            elif isinstance(element, Header):
                elem_type = "header"
            elif isinstance(element, Footer):
                elem_type = "footer"
            elif isinstance(element, Image):
                elem_type = "image"
                has_images = True
                continue  # Skip images for now
            else:
                elem_type = "text"
            
            # Extract metadata
            element_metadata = element.metadata.to_dict() if hasattr(element, 'metadata') else {}
            page_number = element_metadata.get('page_number', 1)
            
            # Track total pages
            if page_number > total_pages:
                total_pages = page_number
            
            # Create extracted element
            extracted_elem = ExtractedElement(
                content=str(element),
                element_type=elem_type,
                page_number=page_number,
                metadata={
                    'coordinates': element_metadata.get('coordinates'),
                    'filetype': element_metadata.get('filetype'),
                    'category': element_metadata.get('category'),
                }
            )
            
            extracted_elements.append(extracted_elem)
        
        logger.info(f"Extracted {len(extracted_elements)} elements from {total_pages} pages")
        
        return DocumentStructure(
            elements=extracted_elements,
            total_pages=total_pages,
            has_tables=has_tables,
            has_images=has_images,
            metadata={
                'extraction_method': 'unstructured',
                'total_elements': len(extracted_elements)
            }
        )
    
    def _extract_with_pymupdf(self, file_path: Path) -> DocumentStructure:
        """
        Fallback extraction using PyMuPDF.
        Simpler but still effective for PDF text extraction.
        """
        doc = fitz.open(file_path)
        extracted_elements = []
        has_tables = False
        
        for page_num, page in enumerate(doc, start=1):
            # Extract text blocks
            blocks = page.get_text("blocks")
            
            for block in blocks:
                # block format: (x0, y0, x1, y1, "text", block_no, block_type)
                if len(block) >= 5:
                    text = block[4].strip()
                    
                    if not text:
                        continue
                    
                    # Simple heuristic: detect tables (blocks with many numbers/pipes)
                    is_table = self._is_likely_table(text)
                    
                    if is_table:
                        has_tables = True
                    
                    extracted_elem = ExtractedElement(
                        content=text,
                        element_type="table" if is_table else "text",
                        page_number=page_num,
                        metadata={
                            'bbox': block[:4],
                            'block_type': block[6] if len(block) > 6 else None
                        }
                    )
                    
                    extracted_elements.append(extracted_elem)
        
        doc.close()
        
        logger.info(f"PyMuPDF extracted {len(extracted_elements)} elements from {len(doc)} pages")
        
        return DocumentStructure(
            elements=extracted_elements,
            total_pages=len(doc),
            has_tables=has_tables,
            has_images=False,
            metadata={
                'extraction_method': 'pymupdf',
                'total_elements': len(extracted_elements)
            }
        )
    
    @staticmethod
    def _is_likely_table(text: str) -> bool:
        """
        Heuristic to detect if text block is likely a table.
        Looks for pipe characters, tabs, and numeric density.
        """
        # Count table indicators
        has_pipes = '|' in text
        has_tabs = '\t' in text
        has_multiple_lines = text.count('\n') >= 2
        
        # Calculate numeric density
        total_chars = len(text.replace(' ', '').replace('\n', ''))
        if total_chars == 0:
            return False
        
        digit_count = sum(c.isdigit() for c in text)
        numeric_density = digit_count / total_chars
        
        # Table if: has formatting AND moderate numeric density
        is_table = (has_pipes or has_tabs) and has_multiple_lines
        is_table = is_table or (numeric_density > 0.3 and has_multiple_lines)
        
        return is_table
    
    def extract_text_only(self, file_path: Path) -> str:
        """
        Extract plain text without structure (faster).
        Useful for simple text files.
        """
        file_ext = file_path.suffix.lower()
        
        if file_ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        elif file_ext == '.pdf':
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        
        else:
            # Use unstructured for other formats
            elements = partition(filename=str(file_path))
            return "\n\n".join(str(elem) for elem in elements)


# Global instance
text_extractor = TextExtractor()

__all__ = ['TextExtractor', 'ExtractedElement', 'DocumentStructure', 'text_extractor']