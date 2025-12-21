"""
Enhanced PDF export service for conversations.
Generates professional, well-structured PDFs with rich formatting.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from io import BytesIO
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether, ListFlowable, ListItem
)
from reportlab.pdfgen import canvas
from loguru import logger


class NumberedCanvas(canvas.Canvas):
    """Custom canvas for page numbering."""
    
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.grey)
        self.drawRightString(
            letter[0] - 40,
            30,
            f"Page {self._pageNumber} of {page_count}"
        )
        self.drawString(
            40,
            30,
            "Novera AI • Confidential"
        )


class EnhancedPDFGenerator:
    """Generate professional, well-structured PDFs from conversation data."""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        
        # Color scheme
        self.primary_color = colors.HexColor('#1e3a8a')      # Dark blue
        self.secondary_color = colors.HexColor('#3b82f6')    # Blue
        self.accent_color = colors.HexColor('#60a5fa')       # Light blue
        self.user_color = colors.HexColor('#059669')         # Green
        self.ai_color = colors.HexColor('#7c3aed')           # Purple
        self.text_color = colors.HexColor('#1f2937')         # Dark gray
        self.light_gray = colors.HexColor('#f3f4f6')
        self.border_color = colors.HexColor('#e5e7eb')
    
    def _setup_custom_styles(self):
        """Create comprehensive custom paragraph styles."""
        
        # Title style
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=28,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=12,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold',
            leading=34
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#6b7280'),
            spaceAfter=24,
            alignment=TA_CENTER,
            fontName='Helvetica',
            leading=16
        ))
        
        # Section header
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold',
            borderWidth=0,
            borderPadding=0,
            leading=20
        ))
        
        # Message header - User
        self.styles.add(ParagraphStyle(
            name='UserHeader',
            parent=self.styles['Heading3'],
            fontSize=11,
            textColor=colors.HexColor('#059669'),
            spaceAfter=6,
            spaceBefore=0,
            fontName='Helvetica-Bold',
            leading=14
        ))
        
        # Message header - AI
        self.styles.add(ParagraphStyle(
            name='AIHeader',
            parent=self.styles['Heading3'],
            fontSize=11,
            textColor=colors.HexColor('#7c3aed'),
            spaceAfter=6,
            spaceBefore=0,
            fontName='Helvetica-Bold',
            leading=14
        ))
        
        # User message content
        self.styles.add(ParagraphStyle(
            name='UserMessage',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1f2937'),
            spaceAfter=4,
            leftIndent=20,
            rightIndent=20,
            fontName='Helvetica',
            leading=15,
            alignment=TA_LEFT
        ))
        
        # AI message content
        self.styles.add(ParagraphStyle(
            name='AIMessage',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            spaceAfter=4,
            leftIndent=20,
            rightIndent=20,
            fontName='Helvetica',
            leading=16,
            alignment=TA_JUSTIFY
        ))
        
        # Bullet point style
        self.styles.add(ParagraphStyle(
            name='BulletPoint',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#374151'),
            leftIndent=35,
            rightIndent=20,
            fontName='Helvetica',
            leading=15,
            spaceAfter=4,
            bulletIndent=20,
            bulletFontSize=10
        ))
        
        # Source citation style
        self.styles.add(ParagraphStyle(
            name='SourceText',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#6b7280'),
            leftIndent=25,
            fontName='Helvetica-Oblique',
            leading=13,
            spaceAfter=2
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='MetadataText',
            parent=self.styles['Normal'],
            fontSize=9,
            textColor=colors.HexColor('#9ca3af'),
            fontName='Helvetica',
            leading=12
        ))
        
        # Info box style
        self.styles.add(ParagraphStyle(
            name='InfoBox',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#1f2937'),
            fontName='Helvetica',
            leading=14,
            leftIndent=10,
            rightIndent=10
        ))
    
    def generate_conversation_pdf(
        self,
        conversation: Dict[str, Any],
        analytics: Optional[Dict[str, Any]] = None
    ) -> BytesIO:
        """
        Generate a professional, well-structured PDF from conversation data.
        """
        buffer = BytesIO()
        
        # Create document with custom canvas for page numbers
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=60,
            leftMargin=60,
            topMargin=60,
            bottomMargin=60,
            title=f"Novera Conversation {conversation['id'][:8]}"
        )
        
        story = []
        
        # Header section
        story.extend(self._create_header_section(conversation))
        
        # Metadata info box
        story.extend(self._create_info_box(conversation, analytics))
        
        # Main separator
        story.append(Spacer(1, 20))
        story.append(HRFlowable(
            width="100%",
            thickness=2,
            color=self.primary_color,
            spaceAfter=20
        ))
        
        # Messages section
        story.extend(self._create_messages_section(conversation))
        
        # Analytics section (if available)
        if analytics:
            story.append(PageBreak())
            story.extend(self._create_analytics_section(analytics))
        
        # Footer
        story.extend(self._create_footer())
        
        # Build PDF with custom canvas
        doc.build(story, canvasmaker=NumberedCanvas)
        
        buffer.seek(0)
        logger.info(f"Generated enhanced PDF for conversation {conversation['id']}")
        return buffer
    
    def _create_header_section(self, conversation: Dict[str, Any]) -> List:
        """Create enhanced header with logo area and title."""
        elements = []
        
        # Logo placeholder (you can add actual logo here)
        # For now, we'll use a styled title box
        
        # Title
        title = Paragraph(
            "Novera AI<br/>Conversation Export",
            self.styles['CustomTitle']
        )
        elements.append(title)
        
        # Date subtitle
        created_date = datetime.fromisoformat(conversation['created_at'])
        subtitle = Paragraph(
            f"Generated on {created_date.strftime('%B %d, %Y at %I:%M %p')}",
            self.styles['CustomSubtitle']
        )
        elements.append(subtitle)
        
        return elements
    
    def _create_info_box(
        self,
        conversation: Dict[str, Any],
        analytics: Optional[Dict[str, Any]]
    ) -> List:
        """Create an information box with key metadata."""
        elements = []
        
        # Prepare data
        total_messages = len(conversation.get('messages', []))
        user_count = len([m for m in conversation['messages'] if m['role'] == 'user'])
        ai_count = len([m for m in conversation['messages'] if m['role'] == 'assistant'])
        
        # Create table data
        data = [
            ['Conversation ID:', conversation['id'][:16] + '...'],
            ['Total Messages:', str(total_messages)],
            ['User Queries:', str(user_count)],
            ['AI Responses:', str(ai_count)],
        ]
        
        if analytics:
            data.append(['Documents Referenced:', str(analytics.get('total_documents', 0))])
            data.append(['Sources Cited:', str(analytics.get('total_sources_cited', 0))])
        
        # Create table
        table = Table(data, colWidths=[2*inch, 4*inch])
        table.setStyle(TableStyle([
            # Background
            ('BACKGROUND', (0, 0), (-1, -1), self.light_gray),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#dbeafe')),
            
            # Text styling
            ('TEXTCOLOR', (0, 0), (-1, -1), self.text_color),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            
            # Alignment
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            
            # Border
            ('BOX', (0, 0), (-1, -1), 1, self.border_color),
            ('LINEBELOW', (0, 0), (-1, -2), 0.5, self.border_color),
        ]))
        
        elements.append(table)
        
        return elements
    
    def _create_messages_section(self, conversation: Dict[str, Any]) -> List:
        """Create well-formatted messages section with proper structure."""
        elements = []
        
        # Section header
        header = Paragraph("Conversation Messages", self.styles['SectionHeader'])
        elements.append(header)
        elements.append(Spacer(1, 10))
        
        messages = conversation.get('messages', [])
        
        for idx, message in enumerate(messages):
            role = message.get('role', 'user')
            content = message.get('content', '')
            timestamp = message.get('timestamp', '')
            metadata = message.get('metadata', {})
            
            # Create message block
            message_elements = []
            
            # Header with timestamp
            if role == 'user':
                header_text = f"👤 <b>User</b> • {self._format_timestamp(timestamp)}"
                header_style = 'UserHeader'
            else:
                header_text = f"🤖 <b>AI Assistant</b> • {self._format_timestamp(timestamp)}"
                header_style = 'AIHeader'
            
            message_header = Paragraph(header_text, self.styles[header_style])
            message_elements.append(message_header)
            
            # Content with proper formatting
            formatted_content = self._format_message_content(
                content,
                role,
                metadata
            )
            message_elements.extend(formatted_content)
            
            # Sources (for AI messages)
            if role == 'assistant' and metadata.get('sources'):
                message_elements.append(Spacer(1, 6))
                sources_header = Paragraph(
                    "<b>📚 Sources:</b>",
                    self.styles['SourceText']
                )
                message_elements.append(sources_header)
                
                for source in metadata['sources'][:5]:
                    doc_name = source.get('document', 'Unknown')
                    page = source.get('page', 'N/A')
                    source_text = f"• {doc_name} (Page {page})"
                    source_para = Paragraph(source_text, self.styles['SourceText'])
                    message_elements.append(source_para)
            
            # Confidence badge
            if role == 'assistant' and metadata.get('confidence'):
                message_elements.append(Spacer(1, 4))
                confidence = metadata['confidence']
                conf_badge = self._create_confidence_badge(confidence)
                message_elements.append(conf_badge)
            
            # Keep message together on same page
            message_block = KeepTogether(message_elements)
            elements.append(message_block)
            
            # Separator
            elements.append(Spacer(1, 12))
            if idx < len(messages) - 1:
                elements.append(HRFlowable(
                    width="90%",
                    thickness=0.5,
                    color=self.border_color,
                    spaceAfter=12
                ))
        
        return elements
    
    def _format_message_content(
        self,
        content: str,
        role: str,
        metadata: Dict[str, Any]
    ) -> List:
        """
        Format message content with proper paragraph and bullet handling.
        """
        elements = []
        
        # Clean content
        content = self._clean_content_for_pdf(content)
        
        # Split into lines for bullet point detection
        lines = content.split('\n')
        
        current_paragraph = []
        in_bullet_list = False
        bullet_items = []
        
        style_name = 'UserMessage' if role == 'user' else 'AIMessage'
        
        for line in lines:
            line = line.strip()
            
            if not line:
                # Empty line - flush current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    elements.append(Paragraph(para_text, self.styles[style_name]))
                    elements.append(Spacer(1, 6))
                    current_paragraph = []
                
                # Flush bullet list
                if bullet_items:
                    elements.extend(self._create_bullet_list(bullet_items))
                    bullet_items = []
                    in_bullet_list = False
                
                continue
            
            # Check if line is a bullet point
            is_bullet = line.startswith('•') or line.startswith('-') or line.startswith('*')
            
            if is_bullet:
                # Flush current paragraph
                if current_paragraph:
                    para_text = ' '.join(current_paragraph)
                    elements.append(Paragraph(para_text, self.styles[style_name]))
                    elements.append(Spacer(1, 6))
                    current_paragraph = []
                
                # Add to bullet list
                bullet_text = line.lstrip('•-* ').strip()
                bullet_items.append(bullet_text)
                in_bullet_list = True
            else:
                # Flush bullet list
                if bullet_items:
                    elements.extend(self._create_bullet_list(bullet_items))
                    bullet_items = []
                    in_bullet_list = False
                
                # Add to paragraph
                current_paragraph.append(line)
        
        # Flush remaining content
        if current_paragraph:
            para_text = ' '.join(current_paragraph)
            elements.append(Paragraph(para_text, self.styles[style_name]))
        
        if bullet_items:
            elements.extend(self._create_bullet_list(bullet_items))
        
        return elements
    
    def _create_bullet_list(self, items: List[str]) -> List:
        """Create a properly formatted bullet list."""
        elements = []
        
        for item in items:
            bullet_para = Paragraph(
                f"• {item}",
                self.styles['BulletPoint']
            )
            elements.append(bullet_para)
        
        elements.append(Spacer(1, 6))
        
        return elements
    
    def _create_confidence_badge(self, confidence: str) -> Table:
        """Create a colored confidence badge."""
        conf_colors = {
            'high': (colors.HexColor('#10b981'), colors.HexColor('#d1fae5')),
            'medium': (colors.HexColor('#f59e0b'), colors.HexColor('#fef3c7')),
            'low': (colors.HexColor('#ef4444'), colors.HexColor('#fee2e2'))
        }
        
        text_color, bg_color = conf_colors.get(confidence, (colors.grey, colors.lightgrey))
        
        badge_text = f"<b>{confidence.upper()} CONFIDENCE</b>"
        
        badge = Table([[Paragraph(badge_text, self.styles['MetadataText'])]], colWidths=[2*inch])
        badge.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), bg_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), text_color),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('BOX', (0, 0), (-1, -1), 1, text_color),
            ('ROUNDEDCORNERS', [4, 4, 4, 4]),
        ]))
        
        return badge
    
    def _create_analytics_section(self, analytics: Dict[str, Any]) -> List:
        """Create detailed analytics section."""
        elements = []
        
        # Title
        title = Paragraph("Conversation Analytics", self.styles['CustomTitle'])
        elements.append(title)
        elements.append(Spacer(1, 20))
        
        # Analytics table
        data = [
            ['Metric', 'Value']
        ]
        
        metrics = [
            ('Total Messages', analytics.get('total_messages', 0)),
            ('User Queries', analytics.get('user_queries', 0)),
            ('AI Responses', analytics.get('ai_responses', 0)),
            ('Documents Referenced', analytics.get('total_documents', 0)),
            ('Total Sources Cited', analytics.get('total_sources_cited', 0)),
            ('Duration', f"{analytics.get('duration_minutes', 0)} minutes"),
        ]
        
        for metric, value in metrics:
            data.append([metric, str(value)])
        
        # Confidence distribution
        conf_dist = analytics.get('confidence_distribution', {})
        if conf_dist:
            data.append(['High Confidence Responses', str(conf_dist.get('high', 0))])
            data.append(['Medium Confidence Responses', str(conf_dist.get('medium', 0))])
            data.append(['Low Confidence Responses', str(conf_dist.get('low', 0))])
        
        table = Table(data, colWidths=[3.5*inch, 2*inch])
        table.setStyle(TableStyle([
            # Header
            ('BACKGROUND', (0, 0), (-1, 0), self.primary_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            
            # Body
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), self.text_color),
            ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            
            # Padding
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            
            # Grid
            ('GRID', (0, 0), (-1, -1), 1, self.border_color),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.light_gray]),
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        # Documents list
        if analytics.get('documents_referenced'):
            docs_header = Paragraph(
                "<b>📄 Documents Referenced:</b>",
                self.styles['SectionHeader']
            )
            elements.append(docs_header)
            elements.append(Spacer(1, 10))
            
            for doc in analytics['documents_referenced']:
                doc_para = Paragraph(f"• {doc}", self.styles['BulletPoint'])
                elements.append(doc_para)
        
        return elements
    
    def _create_footer(self) -> List:
        """Create document footer."""
        elements = []
        
        elements.append(Spacer(1, 30))
        elements.append(HRFlowable(
            width="100%",
            thickness=1,
            color=self.border_color
        ))
        elements.append(Spacer(1, 10))
        
        footer_text = Paragraph(
            f"<i>Generated by Novera AI • {datetime.now().strftime('%B %d, %Y')} • Confidential</i>",
            self.styles['MetadataText']
        )
        elements.append(footer_text)
        
        return elements
    
    def _format_timestamp(self, timestamp: str) -> str:
        """Format ISO timestamp to readable format."""
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime('%I:%M %p')
        except:
            return timestamp
    
    def _clean_content_for_pdf(self, content: str) -> str:
        """Clean and prepare content for PDF rendering."""
        # Remove inline citations
        content = re.sub(r'\[Document:\s*[^\]]+\]', '', content)
        
        # Convert markdown bold to HTML
        content = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', content)
        
        # Convert markdown italic to HTML
        content = re.sub(r'\*(.+?)\*', r'<i>\1</i>', content)
        
        # Escape special XML characters
        content = content.replace('&', '&amp;')
        content = content.replace('<', '&lt;').replace('>', '&gt;')
        
        # Restore HTML tags
        content = content.replace('&lt;b&gt;', '<b>').replace('&lt;/b&gt;', '</b>')
        content = content.replace('&lt;i&gt;', '<i>').replace('&lt;/i&gt;', '</i>')
        
        # Handle very long content
        if len(content) > 8000:
            content = content[:8000] + "\n\n[Content truncated for PDF...]"
        
        return content


# Global instance
pdf_generator = EnhancedPDFGenerator()

__all__ = ['EnhancedPDFGenerator', 'pdf_generator']