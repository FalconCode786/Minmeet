"""
PDF Generation for Meeting Minutes.
Professional, print-ready output.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from datetime import datetime
from typing import List, Dict, Any
import os

class PDFGenerator:
    """
    Generates professional PDF meeting minutes.
    """
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Setup custom paragraph styles."""
        self.styles.add(ParagraphStyle(
            name='MeetingTitle',
            fontSize=24,
            leading=30,
            alignment=TA_CENTER,
            spaceAfter=30,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#1a1a1a')
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            fontSize=14,
            leading=18,
            spaceBefore=20,
            spaceAfter=12,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2c3e50'),
            borderPadding=(0, 0, 5, 0),
            borderWidth=1,
            borderColor=colors.HexColor('#3498db'),
            borderDash=(0, 0, 1, 0)  # Bottom border only
        ))
        
        self.styles.add(ParagraphStyle(
            name='QuestionStyle',
            fontSize=11,
            leading=14,
            leftIndent=20,
            spaceAfter=6,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2c3e50')
        ))
        
        self.styles.add(ParagraphStyle(
            name='AnswerStyle',
            fontSize=10,
            leading=13,
            leftIndent=40,
            spaceAfter=8,
            fontName='Helvetica',
            textColor=colors.HexColor('#555555')
        ))
        
        self.styles.add(ParagraphStyle(
            name='TranscriptEntry',
            fontSize=10,
            leading=13,
            spaceAfter=6,
            fontName='Helvetica'
        ))
        
        self.styles.add(ParagraphStyle(
            name='SpeakerName',
            fontSize=10,
            leading=13,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#2980b9')
        ))
        
        self.styles.add(ParagraphStyle(
            name='Timestamp',
            fontSize=8,
            leading=10,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#7f8c8d')
        ))
        
        self.styles.add(ParagraphStyle(
            name='Footer',
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#7f8c8d')
        ))
    
    def generate(self, meeting_title: str, meeting_date: str, participants: List[str],
                 transcript: List[Dict], qa_pairs: List[Dict], decisions: List[Dict],
                 action_items: List[Dict], output_path: str):
        """
        Generate PDF file.
        """
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        story = []
        
        # Header
        story.append(Paragraph(meeting_title, self.styles['MeetingTitle']))
        
        # Metadata
        meta_data = [
            ['Date:', meeting_date],
            ['Duration:', self._calculate_duration(transcript)],
            ['Participants:', ', '.join(participants[:5]) + ('...' if len(participants) > 5 else '')]
        ]
        
        meta_table = Table(meta_data, colWidths=[1.2*inch, 4*inch])
        meta_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 20))
        
        # Participants Section
        story.append(Paragraph("Participants", self.styles['SectionHeader']))
        for participant in participants:
            story.append(Paragraph(f"• {participant}", self.styles['TranscriptEntry']))
        story.append(Spacer(1, 20))
        
        # Q&A Section
        if qa_pairs:
            story.append(Paragraph("Questions & Answers", self.styles['SectionHeader']))
            for qa in qa_pairs:
                q = qa.get('question', {})
                q_text = q.get('text', '')
                q_speaker = q.get('asked_by', 'Unknown')
                q_time = self._format_timestamp(q.get('timestamp'))
                
                question_para = Paragraph(
                    f"<b>Q ({q_speaker}, {q_time}):</b> {q_text}",
                    self.styles['QuestionStyle']
                )
                story.append(question_para)
                
                for ans in qa.get('answers', []):
                    ans_text = ans.get('text', '')
                    ans_speaker = ans.get('speaker', 'Unknown')
                    ans_time = self._format_timestamp(ans.get('timestamp'))
                    
                    answer_para = Paragraph(
                        f"<b>A ({ans_speaker}, {ans_time}):</b> {ans_text}",
                        self.styles['AnswerStyle']
                    )
                    story.append(answer_para)
                
                story.append(Spacer(1, 10))
            
            story.append(PageBreak())
        
        # Decisions Section
        if decisions:
            story.append(Paragraph("Decisions Made", self.styles['SectionHeader']))
            for i, decision in enumerate(decisions, 1):
                if isinstance(decision, dict):
                    text = decision.get('text', '')
                    speaker = decision.get('speaker', 'Unknown')
                else:
                    text = str(decision)
                    speaker = 'Unknown'
                
                story.append(Paragraph(
                    f"{i}. <b>{speaker}:</b> {text}",
                    self.styles['TranscriptEntry']
                ))
            story.append(Spacer(1, 20))
        
        # Action Items Section
        if action_items:
            story.append(Paragraph("Action Items", self.styles['SectionHeader']))
            
            action_data = [['#', 'Task', 'Assigned To', 'Status']]
            for i, item in enumerate(action_items, 1):
                action_data.append([
                    str(i),
                    item.get('task', '')[:50] + '...' if len(item.get('task', '')) > 50 else item.get('task', ''),
                    item.get('assigned_to', 'Unassigned'),
                    item.get('status', 'Open')
                ])
            
            action_table = Table(action_data, colWidths=[0.3*inch, 3*inch, 1.2*inch, 0.7*inch])
            action_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ecf0f1')),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#bdc3c7')),
                ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(action_table)
            story.append(Spacer(1, 20))
        
        # Transcript Section
        story.append(PageBreak())
        story.append(Paragraph("Full Transcript", self.styles['SectionHeader']))
        
        for entry in transcript:
            speaker = entry.get('speaker', 'Unknown')
            text = entry.get('text', '')
            ts = self._format_timestamp(entry.get('timestamp'))
            is_q = entry.get('is_question', False)
            
            prefix = "<b>Q:</b> " if is_q else ""
            entry_text = f"<b>{speaker}</b> <i>({ts})</i>: {prefix}{text}"
            
            story.append(Paragraph(entry_text, self.styles['TranscriptEntry']))
        
        # Build PDF with footer
        def add_footer(canvas, doc):
            canvas.saveState()
            footer = Paragraph(
                f"Page {doc.page} | Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                self.styles['Footer']
            )
            w, h = footer.wrap(doc.width, doc.bottomMargin)
            footer.drawOn(canvas, doc.leftMargin, 36)
            canvas.restoreState()
        
        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    
    def _format_timestamp(self, ts) -> str:
        """Format timestamp for display."""
        if not ts:
            return "--:--"
        try:
            if isinstance(ts, (int, float)):
                minutes = int(ts / 60)
                seconds = int(ts % 60)
                return f"{minutes:02d}:{seconds:02d}"
            return str(ts)
        except:
            return "--:--"
    
    def _calculate_duration(self, transcript: List[Dict]) -> str:
        """Calculate meeting duration from transcript."""
        if not transcript:
            return "Unknown"
        
        timestamps = [e.get('timestamp', 0) for e in transcript if e.get('timestamp')]
        if not timestamps:
            return "Unknown"
        
        duration_sec = max(timestamps) - min(timestamps)
        minutes = int(duration_sec / 60)
        hours = minutes // 60
        mins = minutes % 60
        
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"