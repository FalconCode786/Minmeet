"""
Minutes Structure Builder.
Assembles transcript, Q&A, decisions into formal meeting minutes.
"""

import json
from datetime import datetime
from typing import List, Dict, Any
from collections import defaultdict

class MinutesBuilder:
    """
    Builds structured meeting minutes from raw data.
    """
    
    def build_minutes(self, transcript: List[Dict], qa_pairs: List[Dict], 
                     decisions: List[Dict], action_items: List[Dict]) -> Dict[str, Any]:
        """
        Construct complete meeting minutes structure.
        """
        # Process Q&A pairs
        processed_qa = self._process_qa_pairs(qa_pairs)
        
        # Extract decisions if not provided
        if not decisions:
            from core.qa_engine import QAProcessor
            qa_engine = QAProcessor()
            decisions = qa_engine.extract_decisions(transcript)
        
        # Extract action items if not provided
        if not action_items:
            from core.qa_engine import QAProcessor
            qa_engine = QAProcessor()
            action_items = qa_engine.extract_action_items(transcript)
        
        # Build chronological log
        discussion_log = self._build_discussion_log(transcript)
        
        # Get unique participants
        participants = list(set(entry.get('speaker', 'Unknown') for entry in transcript))
        
        minutes = {
            'participants': participants,
            'discussion_log': discussion_log,
            'qa_section': processed_qa,
            'decisions': [
                {
                    'timestamp': d.get('timestamp'),
                    'text': d.get('text') if isinstance(d, dict) else str(d),
                    'context': self._get_context_for_entry(d, transcript)
                } for d in decisions
            ],
            'action_items': [
                {
                    'task': item.get('text', ''),
                    'assigned_to': item.get('assigned_to', 'Unassigned'),
                    'timestamp': item.get('timestamp'),
                    'status': 'Open'
                } for item in action_items
            ],
            'summary': self._generate_summary(transcript, len(participants))
        }
        
        return minutes
    
    def _process_qa_pairs(self, qa_pairs: List[Dict]) -> List[Dict]:
        """Process and clean Q&A pairs for minutes."""
        processed = []
        
        for qa in qa_pairs:
            question = qa.get('question', {})
            answers = qa.get('answers', [])
            
            processed_qa = {
                'question': {
                    'text': question.get('text', ''),
                    'asked_by': question.get('speaker', 'Unknown'),
                    'timestamp': question.get('timestamp'),
                    'type': self._categorize_question(question.get('text', ''))
                },
                'answers': [
                    {
                        'text': ans.get('text', ''),
                        'speaker': ans.get('speaker', 'Unknown'),
                        'timestamp': ans.get('timestamp')
                    } for ans in answers
                ],
                'resolved': qa.get('resolved', False)
            }
            
            processed.append(processed_qa)
        
        return processed
    
    def _categorize_question(self, text: str) -> str:
        """Categorize question by type."""
        from core.qa_engine import QAProcessor
        qa = QAProcessor()
        return qa.extract_question_type(text)
    
    def _build_discussion_log(self, transcript: List[Dict]) -> List[Dict]:
        """Build chronological discussion log grouped by topic."""
        # Group by time periods (every 5 minutes)
        time_groups = defaultdict(list)
        
        for entry in transcript:
            ts = entry.get('timestamp', 0)
            # Convert to minutes bucket
            bucket = int(ts / 300) * 5  # 5-minute buckets
            time_groups[bucket].append(entry)
        
        log = []
        for time_bucket in sorted(time_groups.keys()):
            entries = time_groups[time_bucket]
            log.append({
                'time_range': f"{self._format_duration(time_bucket)}-{self._format_duration(time_bucket + 5)}",
                'entries': entries
            })
        
        return log
    
    def _format_duration(self, minutes: int) -> str:
        """Format minutes as HH:MM."""
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours:02d}:{mins:02d}"
    
    def _get_context_for_entry(self, entry: Dict, transcript: List[Dict]) -> str:
        """Get surrounding context for a transcript entry."""
        entry_id = entry.get('id')
        if not entry_id:
            return ""
        
        # Find index
        try:
            idx = next(i for i, e in enumerate(transcript) if e.get('id') == entry_id)
        except StopIteration:
            return ""
        
        # Get 1 before and 1 after
        context = []
        if idx > 0:
            context.append(transcript[idx-1].get('text', ''))
        context.append(entry.get('text', ''))
        if idx < len(transcript) - 1:
            context.append(transcript[idx+1].get('text', ''))
        
        return ' '.join(context)
    
    def _generate_summary(self, transcript: List[Dict], num_participants: int) -> Dict:
        """Generate meeting summary statistics."""
        if not transcript:
            return {}
        
        total_entries = len(transcript)
        questions = sum(1 for e in transcript if e.get('is_question'))
        
        # Estimate duration from timestamps
        timestamps = [e.get('timestamp', 0) for e in transcript if e.get('timestamp')]
        duration = max(timestamps) - min(timestamps) if timestamps else 0
        
        # Speaker participation
        speaker_counts = defaultdict(int)
        for entry in transcript:
            speaker_counts[entry.get('speaker', 'Unknown')] += 1
        
        return {
            'total_entries': total_entries,
            'total_questions': questions,
            'duration_minutes': int(duration / 60),
            'participants': num_participants,
            'participation': dict(speaker_counts)
        }