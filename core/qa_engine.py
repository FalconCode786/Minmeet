"""
Question Detection and Answer Linking Engine.
Uses linguistic patterns and context analysis.
"""

import re
from typing import List, Dict, Any

class QAProcessor:
    """
    Automatically detects questions and links answers.
    No training required - rule-based with heuristics.
    """
    
    def __init__(self):
        # Question indicators
        self.question_starters = [
            'what', 'why', 'how', 'when', 'where', 'who', 'which',
            'whom', 'whose', 'is', 'are', 'was', 'were', 'do', 'does',
            'did', 'can', 'could', 'would', 'should', 'will', 'shall',
            'have', 'has', 'had', 'am', 'may', 'might', 'must'
        ]
        
        self.question_patterns = [
            r'^(what|why|how|when|where|who|which)\s',
            r'^(is|are|was|were|do|does|did|can|could|would|should)\s',
            r'\?$',  # Ends with question mark
            r'^(can you|could you|would you|will you|did you)\s',
            r'^(has anyone|have you|is there|are there)\s',
        ]
        
        # Answer indicators
        self.answer_starters = [
            'yes', 'no', 'sure', 'absolutely', 'definitely',
            'i think', 'in my opinion', 'according to',
            'the reason', 'because', 'since', 'as', 'therefore'
        ]
        
        # Conclusive answer patterns
        self.conclusive_patterns = [
            r'^(yes|no|sure|absolutely|certainly|definitely)\b',
            r'(agreed|confirmed|approved|accepted|decided)\b',
            r'(will do|i\'ll handle|i\'ll take care|assigned to)\b'
        ]
    
    def is_question(self, text: str) -> bool:
        """
        Determine if text is a question using multiple heuristics.
        """
        text_lower = text.lower().strip()
        
        # Check for question mark
        if text.endswith('?'):
            return True
        
        # Check question starters
        words = text_lower.split()
        if words and words[0] in self.question_starters:
            return True
        
        # Check patterns
        for pattern in self.question_patterns:
            if re.search(pattern, text_lower):
                return True
        
        # Structural heuristics
        # Inversion patterns (auxiliary verb before subject)
        aux_verbs = ['is', 'are', 'was', 'were', 'do', 'does', 'did', 'have', 'has', 'had', 'can', 'could', 'would', 'should']
        if len(words) >= 2 and words[0] in aux_verbs:
            return True
        
        return False
    
    def is_answer(self, text: str, context: str = "") -> bool:
        """
        Determine if text is likely an answer to a question.
        """
        text_lower = text.lower().strip()
        
        # Direct answers
        for starter in self.answer_starters:
            if text_lower.startswith(starter):
                return True
        
        # Check if it provides information (declarative statement)
        words = text_lower.split()
        if len(words) > 3 and not self.is_question(text):
            return True
        
        return False
    
    def is_conclusive_answer(self, text: str) -> bool:
        """
        Determine if answer resolves the question definitively.
        Used to mark Q&A pair as resolved.
        """
        text_lower = text.lower().strip()
        
        for pattern in self.conclusive_patterns:
            if re.search(pattern, text_lower):
                return True
        
        # Check for action items or decisions
        if any(word in text_lower for word in ['will', 'schedule', 'set up', 'follow up', 'deadline']):
            return True
        
        return False
    
    def extract_question_type(self, text: str) -> str:
        """
        Categorize question type for better organization.
        """
        text_lower = text.lower()
        
        if any(w in text_lower for w in ['what', 'which']):
            return ' clarification'
        elif any(w in text_lower for w in ['when', 'time', 'date']):
            return ' scheduling'
        elif any(w in text_lower for w in ['who', 'whom']):
            return ' responsibility'
        elif any(w in text_lower for w in ['how']):
            return ' process'
        elif any(w in text_lower for w in ['why']):
            return ' rationale'
        elif any(w in text_lower for w in ['where']):
            return ' location'
        else:
            return ' general'
    
    def link_answer(self, answer: Dict[str, Any], open_questions: List[Dict[str, Any]]) -> int:
        """
        Link answer to most appropriate open question.
        Returns index of linked question or -1.
        """
        if not open_questions:
            return -1
        
        answer_text = answer.get('text', '').lower()
        
        # Score each open question for relevance
        scores = []
        for i, q in enumerate(open_questions):
            question_text = q.get('text', '').lower()
            score = 0
            
            # Word overlap
            answer_words = set(answer_text.split())
            question_words = set(question_text.split())
            overlap = len(answer_words & question_words)
            score += overlap
            
            # Proximity in time (handled by caller, but we weight recent higher)
            score += (len(open_questions) - i) * 0.5
            
            # Contextual clues
            if any(word in answer_text for word in ['it', 'that', 'this', 'they']):
                score += 2  # Pronoun reference likely refers to recent question
            
            scores.append((i, score))
        
        # Return highest scoring question
        if scores:
            best = max(scores, key=lambda x: x[1])
            if best[1] > 0:
                return best[0]
        
        # Default to most recent
        return len(open_questions) - 1 if open_questions else -1
    
    def extract_decisions(self, transcript: List[Dict[str, Any]]) -> List[str]:
        """
        Extract potential decisions from transcript.
        """
        decisions = []
        decision_patterns = [
            r'(we|i|team|group)\s+(have\s+)?(decided|agreed|resolved|concluded)',
            r'(decision|resolution|conclusion)\s+(is|was)',
            r'(moving forward|going forward|from now on)',
            r'(will|shall)\s+(be|use|implement|adopt)',
            r'let\'s\s+(go with|use|choose|select)',
        ]
        
        for entry in transcript:
            text = entry.get('text', '').lower()
            for pattern in decision_patterns:
                if re.search(pattern, text):
                    decisions.append(entry)
                    break
        
        return decisions
    
    def extract_action_items(self, transcript: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract action items from transcript.
        """
        action_items = []
        action_patterns = [
            r'(i will|i\'ll|we will|we\'ll)\s+(.+)',
            r'(need to|needs to|have to|has to)\s+(.+)',
            r'(action item|todo|to-do|task)',
            r'(follow up|followup|check on|review)',
            r'(schedule|set up|arrange|organize)\s+(a|an)?\s*(meeting|call|review)',
        ]
        
        responsible_patterns = [
            r'(john|jane|alex|sarah|mike|emily|chris|lisa|david|anna)',  # Common names
            r'(i|we)\s+will',
        ]
        
        for entry in transcript:
            text = entry.get('text', '').lower()
            speaker = entry.get('speaker', 'Unknown')
            
            for pattern in action_patterns:
                match = re.search(pattern, text)
                if match:
                    # Try to find who is responsible
                    responsible = speaker
                    for resp_pattern in responsible_patterns:
                        resp_match = re.search(resp_pattern, text)
                        if resp_match:
                            if resp_match.group(1) in ['i', 'we']:
                                responsible = speaker
                            else:
                                responsible = resp_match.group(1).title()
                            break
                    
                    action_items.append({
                        'text': entry['text'],
                        'assigned_to': responsible,
                        'timestamp': entry.get('timestamp'),
                        'speaker': speaker
                    })
                    break
        
        return action_items