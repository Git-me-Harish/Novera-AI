"""
Professional corporate-grade PDF export service.
Generates executive-level, publication-quality PDFs with precise formatting.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from io import BytesIO
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, Frame, PageTemplate
)
from reportlab.pdfgen import canvas as pdfcanvas
from loguru import logger


class ProfessionalCanvas(pdfcanvas.Canvas):
    """
    Professional canvas with corporate header/footer.
    Implements consistent branding across all pages.
    """
    
    def __init__(self, *args, **kwargs):
        pdfcanvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []
        self.page_count = 0

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_elements(num_pages)
            pdfcanvas.Canvas.showPage(self)
        pdfcanvas.Canvas.save(self)

    def draw_page_elements(self, page_count):
        """Draw header and footer with professional styling."""
        page_width = letter[0]
        page_height = letter[1]
        
        # Footer - Page numbers and confidentiality notice
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor('#6b7280'))
        
        # Left: Confidential notice
        self.drawString(
            40,
            30,
            "NOVERA AI • CONFIDENTIAL"
        )
        
        # Right: Page number
        self.drawRightString(
            page_width - 40,
            30,
            f"Page {self._pageNumber} of {page_count}"
        )
        
        # Top border line
        self.setStrokeColor(colors.HexColor('#e5e7eb'))
        self.setLineWidth(0.5)
        self.line(40, page_height - 50, page_width - 40, page_height - 50)
        
        # Bottom border line
        self.line(40, 45, page_width - 40, 45)


class CorporatePDFGenerator:
    """
    Corporate-grade PDF generator with executive presentation quality.
    Designed for professional distribution and archival.
    """
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_corporate_styles()
        
        # Professional color palette (corporate blue-gray theme)
        self.primary = colors.HexColor('#1e40af')      # Professional blue
        self.secondary = colors.HexColor('#475569')     # Slate gray
        self.accent = colors.HexColor('#0ea5e9')        # Sky blue
        self.success = colors.HexColor('#059669')       # Emerald green
        self.text_primary = colors.HexColor('#1f2937')  # Near black
        self.text_secondary = colors.HexColor('#6b7280') # Medium gray
        self.bg_light = colors.HexColor('#f8fafc')      # Very light gray
        self.border = colors.HexColor('#e2e8f0')        # Light border
        
        logger.info("Corporate PDF Generator initialized")
    
    def _setup_corporate_styles(self):
        """
        Define corporate typography and styling standards.
        Based on professional document design principles.
        """
        
        # === COVER PAGE STYLES ===
        
        self.styles.add(ParagraphStyle(
            name='CoverTitle',
            parent=self.styles['Heading1'],
            fontSize=32,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=16,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=38
        ))
        
        self.styles.add(ParagraphStyle(
            name='CoverSubtitle',
            parent=self.styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#475569'),
            spaceAfter=8,
            alignment=TA_CENTER,
            fontName='Helvetica',
            leading=18
        ))
        
        # === SECTION STYLES ===
        
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=16,
            spaceBefore=24,
            fontName='Helvetica-Bold',
            leading=22,
            borderPadding=0
        ))
        
        self.styles.add(ParagraphStyle(
            name='SubsectionTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#475569'),
            spaceAfter=12,
            spaceBefore=16,
            fontName='Helvetica-Bold',
            leading=18
        ))
        
        # === MESSAGE STYLES ===
        
        self.styles.add(ParagraphStyle(
            name='MessageHeader',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#475569'),
            spaceAfter=8,
            fontName='Helvetica-Bold',
            leading=14
        ))
        
        self.styles.add(ParagraphStyle(
            name='MessageBody',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=6,
            leftIndent=0,
            rightIndent=0,
            fontName='Helvetica',
            leading=16,
            alignment=TA_JUSTIFY
        ))
        
        self.styles.add(ParagraphStyle(
            name='BulletItem',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            leftIndent=24,
            bulletIndent=12,
            fontName='Helvetica',
            leading=16,
            spaceAfter=6
        ))
        
        # === METADATA STYLES ===
        
        self.styles.add(ParagraphStyle(
            name='MetadataLabel',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#6b7280'),
            fontName='Helvetica-Bold',
            leading=13
        ))
        
        self.styles.add(ParagraphStyle(
            name='MetadataValue',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#374151'),
            fontName='Helvetica',
            leading=13
        ))
        
        self.styles.add(ParagraphStyle(
            name='SourceCitation',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#6b7280'),
            fontName='Helvetica-Oblique',
            leading=12,
            leftIndent=16
        ))
    
    def generate_conversation_pdf(
        self,
        conversation: Dict[str, Any],
        analytics: Optional[Dict[str, Any]] = None
    ) -> BytesIO:
        """
        Generate professional, publication-quality PDF.
        
        Structure:
        1. Cover page with metadata
        2. Executive summary (if analytics provided)
        3. Conversation transcript
        4. Analytics appendix (if provided)
        """
        buffer = BytesIO()
        
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=72,      # 1 inch margins
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
            title=f"Novera AI - Conversation Report",
            author="Novera AI System"
        )
        
        story = []
        
        # === COVER PAGE ===
        story.extend(self._create_cover_page(conversation))
        story.append(PageBreak())
        
        # === EXECUTIVE SUMMARY ===
        if analytics:
            story.extend(self._create_executive_summary(conversation, analytics))
            story.append(PageBreak())
        
        # === CONVERSATION TRANSCRIPT ===
        story.extend(self._create_conversation_section(conversation))
        
        # === ANALYTICS APPENDIX ===
        if analytics:
            story.append(PageBreak())
            story.extend(self._create_analytics_appendix(analytics))
        
        # Build PDF
        doc.build(story, canvasmaker=ProfessionalCanvas)
        
        buffer.seek(0)
        logger.info(f"Generated professional PDF: {len(conversation.get('messages', []))} messages")
        return buffer
    
    def _create_cover_page(self, conversation: Dict[str, Any]) -> List:
        """
        Create professional cover page with corporate branding.
        """
        elements = []
        
        # Top spacing
        elements.append(Spacer(1, 1.5*inch))
        
        # Company/Product name
        elements.append(Paragraph(
            "NOVERA AI",
            self.styles['CoverTitle']
        ))
        
        # Document type
        elements.append(Paragraph(
            "Conversation Analysis Report",
            self.styles['CoverSubtitle']
        ))
        
        elements.append(Spacer(1, 0.5*inch))
        
        # Decorative line
        elements.append(HRFlowable(
            width="40%",
            thickness=2,
            color=self.primary,
            spaceAfter=32,
            spaceBefore=0,
            hAlign='CENTER'
        ))
        
        elements.append(Spacer(1, 0.75*inch))
        
        # Metadata table
        metadata = conversation.get('metadata', {})
        created_date = datetime.fromisoformat(conversation['created_at'])
        
        data = [
            ['Conversation ID', conversation['id'][:24] + '...'],
            ['Date Generated', created_date.strftime('%B %d, %Y')],
            ['Time Generated', created_date.strftime('%I:%M %p')],
            ['Total Messages', str(len(conversation.get('messages', [])))],
        ]
        
        # Add selective export info if present
        if metadata.get('is_selective_export'):
            data.append([
                'Export Type',
                f"Selective ({metadata.get('exported_message_count', 0)} of {metadata.get('total_messages_in_conversation', 0)} messages)"
            ])
        
        table = Table(data, colWidths=[2.5*inch, 3*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.bg_light),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.text_primary),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 16),
            ('RIGHTPADDING', (0, 0), (-1, -1), 16),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('BOX', (0, 0), (-1, -1), 1, self.border),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, self.border),
        ]))
        
        elements.append(table)
        
        # Bottom spacing and confidentiality notice
        elements.append(Spacer(1, 2*inch))
        elements.append(Paragraph(
            "<i>CONFIDENTIAL - FOR AUTHORIZED USE ONLY</i>",
            self.styles['MetadataLabel']
        ))
        
        return elements
    
    def _create_executive_summary(
        self,
        conversation: Dict[str, Any],
        analytics: Dict[str, Any]
    ) -> List:
        """Create executive summary with key metrics."""
        elements = []
        
        elements.append(Paragraph("EXECUTIVE SUMMARY", self.styles['SectionTitle']))
        elements.append(Spacer(1, 16))
        
        # Key metrics in grid layout
        metrics = [
            ['Metric', 'Value', 'Details'],
            [
                'Total Exchanges',
                str(analytics.get('user_queries', 0)),
                'User questions asked'
            ],
            [
                'AI Responses',
                str(analytics.get('ai_responses', 0)),
                'Answers provided'
            ],
            [
                'Documents Referenced',
                str(analytics.get('total_documents', 0)),
                'Unique documents consulted'
            ],
            [
                'Source Citations',
                str(analytics.get('total_sources_cited', 0)),
                'Total citations provided'
            ],
            [
                'Duration',
                f"{analytics.get('duration_minutes', 0)} min",
                'Conversation length'
            ],
        ]
        
        table = Table(metrics, colWidths=[2*inch, 1.2*inch, 2.3*inch])
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), self.primary),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.text_primary),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),
            
            # Styling
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, self.border),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.bg_light]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 24))
        
        # Confidence distribution
        conf_dist = analytics.get('confidence_distribution', {})
        if conf_dist:
            elements.append(Paragraph("Response Quality", self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 8))
            
            conf_data = [
                ['Quality Level', 'Count', 'Percentage'],
                [
                    'High Confidence',
                    str(conf_dist.get('high', 0)),
                    f"{self._percentage(conf_dist.get('high', 0), analytics.get('ai_responses', 1))}%"
                ],
                [
                    'Medium Confidence',
                    str(conf_dist.get('medium', 0)),
                    f"{self._percentage(conf_dist.get('medium', 0), analytics.get('ai_responses', 1))}%"
                ],
                [
                    'Low Confidence',
                    str(conf_dist.get('low', 0)),
                    f"{self._percentage(conf_dist.get('low', 0), analytics.get('ai_responses', 1))}%"
                ],
            ]
            
            conf_table = Table(conf_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
            conf_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.secondary),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('GRID', (0, 0), (-1, -1), 0.5, self.border),
            ]))
            
            elements.append(conf_table)
        
        return elements
    
    def _create_conversation_section(self, conversation: Dict[str, Any]) -> List:
        """
        Create conversation transcript with professional message formatting.
        Preserves tables, lists, and formatting from original content.
        """
        elements = []
        
        elements.append(Paragraph("CONVERSATION TRANSCRIPT", self.styles['SectionTitle']))
        elements.append(Spacer(1, 16))
        
        messages = conversation.get('messages', [])
        
        for idx, message in enumerate(messages, 1):
            role = message.get('role', 'user')
            content = message.get('content', '')
            timestamp = message.get('timestamp', '')
            metadata = message.get('metadata', {})
            
            # Create message container
            message_elements = []
            
            # === MESSAGE HEADER ===
            header_parts = []
            
            if role == 'user':
                header_parts.append(f"<b>USER QUERY #{idx}</b>")
            else:
                header_parts.append(f"<b>AI RESPONSE #{idx}</b>")
            
            if timestamp:
                formatted_time = self._format_timestamp(timestamp)
                header_parts.append(f"• {formatted_time}")
            
            header_text = " ".join(header_parts)
            message_elements.append(Paragraph(header_text, self.styles['MessageHeader']))
            message_elements.append(Spacer(1, 4))
            
            # === MESSAGE CONTENT ===
            # Parse and format content (handles tables, lists, paragraphs)
            content_elements = self._parse_message_content(content, role)
            message_elements.extend(content_elements)
            
            # === SOURCES (AI messages only) ===
            if role == 'assistant' and metadata.get('sources'):
                message_elements.append(Spacer(1, 8))
                message_elements.append(Paragraph(
                    "<b>Sources Referenced:</b>",
                    self.styles['MetadataLabel']
                ))
                message_elements.append(Spacer(1, 4))
                
                for source in metadata['sources'][:5]:
                    doc_name = source.get('document', 'Unknown Document')
                    page = source.get('page', 'N/A')
                    section = source.get('section')
                    
                    source_text = f"• {doc_name}"
                    if page != 'N/A':
                        source_text += f", Page {page}"
                    if section:
                        source_text += f", Section: {section}"
                    
                    message_elements.append(Paragraph(
                        source_text,
                        self.styles['SourceCitation']
                    ))
            
            # === CONFIDENCE BADGE (AI messages only) ===
            if role == 'assistant' and metadata.get('confidence'):
                message_elements.append(Spacer(1, 6))
                badge = self._create_confidence_indicator(metadata['confidence'])
                message_elements.append(badge)
            
            # Keep message together
            message_block = KeepTogether(message_elements)
            elements.append(message_block)
            
            # Separator between messages
            elements.append(Spacer(1, 16))
            if idx < len(messages):
                elements.append(HRFlowable(
                    width="100%",
                    thickness=0.5,
                    color=self.border,
                    spaceAfter=16
                ))
        
        return elements
    
    def _parse_message_content(self, content: str, role: str) -> List:
        """
        Parse message content and extract:
        - Tables (markdown tables)
        - Bullet lists
        - Numbered lists
        - Paragraphs
        - Bold/italic formatting
        
        Preserves all formatting in professional layout.
        """
        elements = []
        
        # Clean content
        content = self._clean_content(content)
        
        # Split into blocks (separated by blank lines)
        blocks = re.split(r'\n\s*\n', content)
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            # Check if block is a table
            if '|' in block and block.count('|') >= 3:
                table_elem = self._parse_table(block)
                if table_elem:
                    elements.append(table_elem)
                    elements.append(Spacer(1, 12))
                    continue
            
            # Check if block is a bullet list
            lines = block.split('\n')
            if all(line.strip().startswith(('-', '•', '*')) for line in lines if line.strip()):
                list_elements = self._parse_bullet_list(lines)
                elements.extend(list_elements)
                elements.append(Spacer(1, 8))
                continue
            
            # Check if block is numbered list
            if re.match(r'^\d+\.', lines[0].strip()):
                list_elements = self._parse_numbered_list(lines)
                elements.extend(list_elements)
                elements.append(Spacer(1, 8))
                continue
            
            # Regular paragraph
            para_text = ' '.join(line.strip() for line in lines)
            para_text = self._format_inline_text(para_text)
            
            elements.append(Paragraph(para_text, self.styles['MessageBody']))
            elements.append(Spacer(1, 6))
        
        return elements
    
    def _parse_table(self, table_text: str) -> Optional[Table]:
        """
        Parse markdown table and create professional ReportLab table.
        
        Example input:
        | Header 1 | Header 2 |
        |----------|----------|
        | Value 1  | Value 2  |
        """
        lines = [line.strip() for line in table_text.split('\n') if line.strip()]
        
        # Remove separator line (usually second line with dashes)
        lines = [line for line in lines if not re.match(r'^\|[\s\-|]+\|$', line)]
        
        if len(lines) < 2:
            return None
        
        # Parse rows
        data = []
        for line in lines:
            # Split by | and clean
            cells = [cell.strip() for cell in line.split('|') if cell.strip()]
            if cells:
                data.append(cells)
        
        if not data:
            return None
        
        # Determine column widths
        num_cols = len(data[0])
        available_width = 5.5 * inch
        col_width = available_width / num_cols
        
        table = Table(data, colWidths=[col_width] * num_cols)
        table.setStyle(TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), self.primary),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            
            # Body rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.text_primary),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            
            # Styling
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, self.border),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.bg_light]),
        ]))
        
        return table
    
    def _parse_bullet_list(self, lines: List[str]) -> List:
        """Parse bullet list into formatted elements."""
        elements = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove bullet marker
            text = re.sub(r'^[\-•*]\s*', '', line)
            text = self._format_inline_text(text)
            
            elements.append(Paragraph(f"• {text}", self.styles['BulletItem']))
        
        return elements
    
    def _parse_numbered_list(self, lines: List[str]) -> List:
        """Parse numbered list into formatted elements."""
        elements = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Extract number and text
            match = re.match(r'^(\d+)\.\s*(.+)$', line)
            if match:
                num, text = match.groups()
                text = self._format_inline_text(text)
                elements.append(Paragraph(f"{num}. {text}", self.styles['BulletItem']))
        
        return elements
    
    def _format_inline_text(self, text: str) -> str:
        """
        Format inline markdown:
        - **bold** → <b>bold</b>
        - *italic* → <i>italic</i>
        """
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        # Escape XML
        text = text.replace('&', '&amp;')
        # Restore tags
        text = text.replace('&amp;lt;', '<').replace('&amp;gt;', '>')
        
        return text
    
    def _clean_content(self, content: str) -> str:
        """Remove inline citations and prepare content."""
        # Remove [Document: X, Page: Y] citations
        content = re.sub(r'\[Document:[^\]]+\]', '', content)
        return content.strip()
    
    def _create_confidence_indicator(self, confidence: str) -> Table:
        """Create minimal, professional confidence indicator."""
        conf_colors = {
            'high': (self.success, colors.HexColor('#d1fae5')),
            'medium': (colors.HexColor('#f59e0b'), colors.HexColor('#fef3c7')),
            'low': (colors.HexColor('#ef4444'), colors.HexColor('#fee2e2'))
        }
        
        text_color, bg_color = conf_colors.get(confidence, (self.text_secondary, self.bg_light))
        
        badge = Table([[Paragraph(
            f"<b>CONFIDENCE: {confidence.upper()}</b>",
            self.styles['MetadataLabel']
        )]], colWidths=[1.8*inch])
        
        badge.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), text_color),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('BOX', (0, 0), (-1, -1), 0.5, text_color),
        ]))
        
        return badge
    
    def _create_analytics_appendix(self, analytics: Dict[str, Any]) -> List:
        """Create detailed analytics appendix."""
        elements = []
        
        elements.append(Paragraph("APPENDIX: DETAILED ANALYTICS", self.styles['SectionTitle']))
        elements.append(Spacer(1, 16))
        
        # Documents referenced
        if analytics.get('documents_referenced'):
            elements.append(Paragraph("Documents Consulted", self.styles['SubsectionTitle']))
            elements.append(Spacer(1, 8))
            
            for idx, doc in enumerate(analytics['documents_referenced'], 1):
                elements.append(Paragraph(
                    f"{idx}. {doc}",
                    self.styles['BulletItem']
                ))
            
            elements.append(Spacer(1, 16))
        
        # Primary document
        if analytics.get('primary_document'):
            elements.append(Paragraph(
                f"<b>Primary Focus Document:</b> {analytics['primary_document']}",
                self.styles['MetadataValue']
            ))
            elements.append(Spacer(1, 8))
        
        return elements
    
    def _format_timestamp(self, timestamp: str) -> str:
        """Format timestamp to readable format."""
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime('%B %d, %Y at %I:%M %p')
        except:
            return timestamp
    
    def _percentage(self, value: int, total: int) -> int:
        """Calculate percentage safely."""
        if total == 0:
            return 0
        return int((value / total) * 100)


# Global instance
pdf_generator = CorporatePDFGenerator()

__all__ = ['CorporatePDFGenerator', 'pdf_generator']