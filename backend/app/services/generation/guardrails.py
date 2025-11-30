"""
Guardrails service for input and output validation.
Implements safety checks, hallucination detection, and content filtering.
"""
from typing import Dict, Any, List, Optional, Tuple
import re
from loguru import logger

from app.core.config import settings


class GuardrailsService:
    """
    Service for validating inputs and outputs to ensure safety and accuracy.
    Implements multiple layers of protection.
    """
    
    def __init__(self):
        self.input_enabled = settings.enable_input_guardrails
        self.output_enabled = settings.enable_output_guardrails
        self.hallucination_threshold = settings.hallucination_threshold
        
        # Jailbreak patterns
        self.jailbreak_patterns = [
            r'ignore previous instructions',
            r'disregard .* rules',
            r'act as (?:if|though)',
            r'pretend (?:to be|you are)',
            r'bypass restrictions',
            r'override system prompt'
        ]
        
        # Sensitive data patterns
        self.pii_patterns = {
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'credit_card': r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'
        }
        
        # Off-topic indicators
        self.off_topic_keywords = [
            'weather', 'recipe', 'travel', 'entertainment', 'sports',
            'news', 'politics', 'celebrity', 'joke', 'story'
        ]
        
        logger.info(f"Guardrails initialized: input={self.input_enabled}, output={self.output_enabled}")
    
    def validate_input(self, query: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate user input query.
        
        Args:
            query: User's query
            metadata: Optional metadata (user info, session, etc.)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.input_enabled:
            return True, None
        
        logger.debug(f"Validating input: '{query[:50]}...'")
        
        # 1. Check for jailbreak attempts
        is_jailbreak, jailbreak_msg = self._detect_jailbreak(query)
        if is_jailbreak:
            logger.warning(f"❌ Jailbreak detected: {jailbreak_msg}")
            return False, "Query contains prohibited instructions"
        
        # 2. Check for PII
        has_pii, pii_type = self._detect_pii(query)
        if has_pii:
            logger.warning(f"❌ PII detected: {pii_type}")
            return False, f"Please remove {pii_type} information from your query"
        
        # 3. Check if on-topic
        is_relevant = self._check_topic_relevance(query)
        if not is_relevant:
            logger.warning(f"⚠️  Off-topic query detected")
            return False, "This query appears to be outside the scope of finance/HRMS documentation. Please ask questions related to company policies, financial reports, or HR procedures."
        
        # 4. Check length
        if len(query) > 1000:
            logger.warning("❌ Query too long")
            return False, "Query is too long. Please limit to 1000 characters."
        
        if len(query.strip()) < 3:
            logger.warning("❌ Query too short")
            return False, "Query is too short. Please provide more detail."
        
        logger.debug("✅ Input validation passed")
        return True, None
    
    def validate_output(
        self,
        query: str,
        answer: str,
        context: str,
        sources: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate generated output for hallucinations and quality.
        
        Args:
            query: Original query
            answer: Generated answer
            context: Context used for generation
            sources: Source documents
            
        Returns:
            Tuple of (is_valid, warning_message, validation_details)
        """
        if not self.output_enabled:
            return True, None, {}
        
        logger.debug("Validating output...")
        
        validation_details = {}
        
        # 1. Check for hallucination
        hallucination_score = self._detect_hallucination(answer, context)
        validation_details['hallucination_score'] = hallucination_score
        
        if hallucination_score > self.hallucination_threshold:
            logger.warning(f"❌ High hallucination score: {hallucination_score:.2f}")
            return False, "Answer may contain unverified information", validation_details
        
        # 2. Check source attribution
        has_citations = self._check_citations(answer, sources)
        validation_details['has_citations'] = has_citations
        
        if not has_citations and len(sources) > 0:
            logger.warning("⚠️  Answer missing citations")
            validation_details['warning'] = "Answer should include source citations"
        
        # 3. Check for speculation
        has_speculation = self._detect_speculation(answer)
        validation_details['has_speculation'] = has_speculation
        
        if has_speculation:
            logger.warning("⚠️  Answer contains speculative language")
            validation_details['warning'] = "Answer contains uncertainty"
        
        # 4. Check answer length
        if len(answer.strip()) < 20:
            logger.warning("⚠️  Answer too short")
            return False, "Generated answer is too brief", validation_details
        
        logger.debug("✅ Output validation passed")
        return True, None, validation_details
    
    def _detect_jailbreak(self, query: str) -> Tuple[bool, Optional[str]]:
        """
        Detect jailbreak/prompt injection attempts.
        
        Returns:
            Tuple of (is_jailbreak, description)
        """
        query_lower = query.lower()
        
        for pattern in self.jailbreak_patterns:
            if re.search(pattern, query_lower):
                return True, f"Pattern matched: {pattern}"
        
        return False, None
    
    def _detect_pii(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Detect personally identifiable information.
        
        Returns:
            Tuple of (has_pii, pii_type)
        """
        for pii_type, pattern in self.pii_patterns.items():
            if re.search(pattern, text):
                return True, pii_type
        
        return False, None
    
    def _check_topic_relevance(self, query: str) -> bool:
        """
        Check if query is relevant to finance/HRMS domain.
        
        Returns:
            True if relevant, False if off-topic
        """
        query_lower = query.lower()
        
        # Check for obvious off-topic keywords
        off_topic_count = sum(
            1 for keyword in self.off_topic_keywords
            if keyword in query_lower
        )
        
        # If multiple off-topic keywords, likely irrelevant
        if off_topic_count >= 2:
            return False
        
        # Check for domain keywords
        domain_keywords = [
            'salary', 'payroll', 'leave', 'policy', 'expense', 'revenue',
            'profit', 'budget', 'employee', 'hr', 'finance', 'benefit',
            'reimbursement', 'tax', 'allowance', 'compensation', 'report',
            'quarter', 'annual', 'department', 'cost', 'payment'
        ]
        
        has_domain_keyword = any(
            keyword in query_lower for keyword in domain_keywords
        )
        
        # If has domain keyword, consider relevant
        if has_domain_keyword:
            return True
        
        # If no clear off-topic indicators and reasonable length, allow it
        return len(query.split()) >= 3
    
    def _detect_hallucination(self, answer: str, context: str) -> float:
        """
        Detect potential hallucinations by comparing answer to context.
        
        Returns:
            Hallucination score (0-1, higher = more likely hallucinated)
        """
        # Extract numerical claims from answer
        numbers_in_answer = re.findall(r'\$?[\d,]+(?:\.\d+)?%?', answer)
        
        hallucination_indicators = 0
        total_checks = 0
        
        # Check if numbers in answer exist in context
        for number in numbers_in_answer:
            total_checks += 1
            if number not in context:
                hallucination_indicators += 1
        
        # Check for hedging language (indicates model uncertainty)
        hedging_phrases = [
            'i think', 'i believe', 'probably', 'possibly',
            'it seems', 'appears to be', 'might be'
        ]
        
        answer_lower = answer.lower()
        has_hedging = any(phrase in answer_lower for phrase in hedging_phrases)
        
        if has_hedging:
            hallucination_indicators += 1
            total_checks += 1
        
        # Calculate score
        if total_checks == 0:
            return 0.0
        
        score = hallucination_indicators / total_checks
        
        return score
    
    def _check_citations(self, answer: str, sources: List[Dict[str, Any]]) -> bool:
        """
        Check if answer includes proper citations.
        
        Returns:
            True if citations present
        """
        # Look for citation patterns
        citation_patterns = [
            r'\[Document:',
            r'\[Source:',
            r'\(Page \d+\)',
            r'according to',
            r'as stated in'
        ]
        
        has_citation = any(
            re.search(pattern, answer, re.IGNORECASE)
            for pattern in citation_patterns
        )
        
        return has_citation
    
    def _detect_speculation(self, answer: str) -> bool:
        """
        Detect speculative or uncertain language.
        
        Returns:
            True if speculation detected
        """
        speculation_indicators = [
            'may', 'might', 'could', 'possibly', 'perhaps',
            'it seems', 'appears to', 'likely', 'probably'
        ]
        
        answer_lower = answer.lower()
        
        return any(indicator in answer_lower for indicator in speculation_indicators)
    
    def sanitize_output(self, text: str) -> str:
        """
        Sanitize output text by removing any leaked system prompts or internal markers.
        
        Returns:
            Sanitized text
        """
        # Remove common system prompt leakage patterns
        patterns_to_remove = [
            r'System:.*?\n',
            r'Assistant:.*?\n',
            r'You are an AI.*?\n',
            r'\[INTERNAL\].*?\[/INTERNAL\]'
        ]
        
        sanitized = text
        for pattern in patterns_to_remove:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE | re.DOTALL)
        
        return sanitized.strip()


# Global instance
guardrails_service = GuardrailsService()

__all__ = ['GuardrailsService', 'guardrails_service']