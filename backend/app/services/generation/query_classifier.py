"""
Pure LLM-based intelligent query classification.
Zero hardcoded rules - only semantic understanding.
"""
from typing import Dict, Any, Optional
import asyncio
import google.generativeai as genai
from loguru import logger

from app.core.config import settings


class QueryClassifier:
    """
    Pure LLM-based query classifier.
    No hardcoded keywords - pure semantic understanding.
    """
    
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        
        raw_model_name = settings.gemini_chat_model
        if raw_model_name.startswith('models/'):
            model_name = raw_model_name.replace('models/', '', 1)
        else:
            model_name = raw_model_name
        
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 0.0,  # Deterministic classification
                "max_output_tokens": 100,
            }
        )
    
    async def classify_query(self, query: str, conversation_history: Optional[list] = None) -> Dict[str, Any]:
        """
        Classify query using pure LLM understanding.
        
        Args:
            query: User's query
            conversation_history: Recent conversation for context
            
        Returns:
            {
                'type': 'conversational' or 'document',
                'reasoning': explanation of decision,
                'confidence': 'high', 'medium', 'low'
            }
        """
        
        # Build context from history if available
        history_context = ""
        if conversation_history and len(conversation_history) > 0:
            recent_msgs = conversation_history[-2:]
            history_context = "\n\nRecent conversation context:\n"
            for msg in recent_msgs:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                history_context += f"{role.capitalize()}: {content}\n"
        
        # Pure understanding-based prompt
        classification_prompt = f"""You are analyzing a user query to determine if it needs document search or conversational response.

**Your Identity Context:**
You are Novera, an AI assistant specialized in Finance and HRMS documentation. You help users find information from their company documents like policies, financial reports, HR manuals, etc.

**Task:**
Analyze the user's query and determine:
- Is the user asking about YOU (your identity, capabilities, how you work)?
- OR is the user asking for INFORMATION that would be in their company documents?

**Guidelines:**

CONVERSATIONAL queries are when users ask:
- About your identity (who/what you are, your name, your purpose)
- About your capabilities (what you can do, how you help, your features)
- About how you work (your functionality, your knowledge)
- General greetings, thanks, small talk
- Questions directed at you as an AI assistant

DOCUMENT queries are when users ask:
- For specific information from company documents
- About company policies, procedures, rules, guidelines
- About financial data, reports, numbers, budgets
- About employee information, benefits, salaries, leaves
- For explanations of company-specific topics
- For data that exists in documents (even if not explicitly mentioned)

**Critical Understanding:**
- "What are your capabilities?" = asking about YOU → CONVERSATIONAL
- "What capabilities do employees have?" = asking about DOCUMENTS → DOCUMENT
- "Tell me about yourself" = asking about YOU → CONVERSATIONAL
- "Tell me about the leave policy" = asking about DOCUMENTS → DOCUMENT
- "How can you help?" = asking about YOU → CONVERSATIONAL
- "How can I apply for leave?" = asking about DOCUMENTS → DOCUMENT

**The Query:**{history_context}

Current query: "{query}"

**Your Analysis:**
Think step by step:
1. What is the user actually asking about?
2. Are they asking about me (Novera the AI) or about their company information?
3. Would answering this require searching company documents?

Respond in this EXACT format:
TYPE: [CONVERSATIONAL or DOCUMENT]
REASONING: [one sentence explanation]
CONFIDENCE: [HIGH or MEDIUM or LOW]"""

        try:
            loop = asyncio.get_event_loop()
            
            response = await loop.run_in_executor(
                None,
                lambda: self.model.generate_content(classification_prompt)
            )
            
            result_text = response.text.strip()
            
            # Parse the structured response
            classification_type = 'document'  # safe default
            reasoning = 'Unable to parse classification'
            confidence = 'medium'
            
            for line in result_text.split('\n'):
                line = line.strip()
                if line.startswith('TYPE:'):
                    type_value = line.replace('TYPE:', '').strip().upper()
                    if 'CONVERSATIONAL' in type_value:
                        classification_type = 'conversational'
                    elif 'DOCUMENT' in type_value:
                        classification_type = 'document'
                
                elif line.startswith('REASONING:'):
                    reasoning = line.replace('REASONING:', '').strip()
                
                elif line.startswith('CONFIDENCE:'):
                    conf_value = line.replace('CONFIDENCE:', '').strip().upper()
                    if 'HIGH' in conf_value:
                        confidence = 'high'
                    elif 'LOW' in conf_value:
                        confidence = 'low'
                    else:
                        confidence = 'medium'
            
            logger.info(f"🎯 Query: '{query}'")
            logger.info(f"   Classification: {classification_type.upper()}")
            logger.info(f"   Reasoning: {reasoning}")
            logger.info(f"   Confidence: {confidence}")
            
            return {
                'type': classification_type,
                'reasoning': reasoning,
                'confidence': confidence
            }
            
        except Exception as e:
            logger.error(f"Classification failed: {str(e)}, defaulting to DOCUMENT")
            return {
                'type': 'document',
                'reasoning': f'Classification error: {str(e)}',
                'confidence': 'low'
            }


# Global instance
query_classifier = QueryClassifier()

__all__ = ['QueryClassifier', 'query_classifier']