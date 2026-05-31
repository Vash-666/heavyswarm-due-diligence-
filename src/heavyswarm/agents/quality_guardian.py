"""Quality Guardian Agent - Conditional Quality Gate."""

import json
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class QualityGuardianAgent(BaseAgent):
    """Agent that performs conditional high-stakes review.
    
    This is the Quality Gate of the HeavySwarm workflow. It is triggered
    when confidence is low, risk is high, or anomalies are detected.
    """
    
    # Trigger conditions
    CONFIDENCE_THRESHOLD = 0.85
    RISK_SCORE_THRESHOLD = 70
    POSITION_SIZE_THRESHOLD = 0.05
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the quality guardian agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.QUALITY_GUARDIAN
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    def should_trigger(self, state: Any) -> bool:
        """Determine if quality gate should be triggered.
        
        Args:
            state: Current diligence state
            
        Returns:
            True if quality gate should trigger
        """
        # Check confidence threshold
        if hasattr(state, 'overall_confidence') and state.overall_confidence < self.CONFIDENCE_THRESHOLD:
            return True
        
        # Check position size threshold
        if hasattr(state, 'thesis') and state.thesis and state.thesis.position_size > self.POSITION_SIZE_THRESHOLD:
            return True
        
        # Check for quality gate flag
        if hasattr(state, 'quality_gate_triggered') and state.quality_gate_triggered:
            return True
        
        # Check risk score
        risk_output = getattr(state, 'phase_results', {}).get(AgentPhase.RISK_ANALYST, {})
        risk_score = risk_output.get('data', {}).get('risk_score', {}).get('overall', 0)
        if risk_score > self.RISK_SCORE_THRESHOLD:
            return True
        
        return False
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute quality review using LLM.
        
        Args:
            input_data: Input containing full analysis and memo
            
        Returns:
            Agent output with approve/reject/escalate decision
        """
        logger.info(
            "QualityGuardian executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        
        # Get all data
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        
        verifier_output = previous_phases.get("VERIFIER", {})
        confidence_score = verifier_output.get("confidence_score", {})
        
        risk_output = previous_phases.get("RISK_ANALYST", {})
        risk_score = risk_output.get("risk_score", {})
        
        # Determine trigger reason
        trigger_reasons = []
        if confidence_score.get("overall", 1.0) < self.CONFIDENCE_THRESHOLD:
            trigger_reasons.append(f"Confidence {confidence_score.get('overall', 0):.0%} < {self.CONFIDENCE_THRESHOLD:.0%}")
        if risk_score.get("overall", 0) > self.RISK_SCORE_THRESHOLD:
            trigger_reasons.append(f"Risk score {risk_score.get('overall', 0)} > {self.RISK_SCORE_THRESHOLD}")
        if input_data.thesis and input_data.thesis.position_size > self.POSITION_SIZE_THRESHOLD:
            trigger_reasons.append(f"Position size {input_data.thesis.position_size:.1%} > {self.POSITION_SIZE_THRESHOLD:.1%}")
        
        trigger_reason = "; ".join(trigger_reasons) if trigger_reasons else "Manual trigger"
        
        # Perform quality review using LLM
        review = await self._perform_quality_review(
            ticker,
            previous_phases,
            confidence_score,
            risk_score,
            trigger_reason,
        )
        
        output_data = {
            "review_decision": review.get("decision", "escalate"),
            "decision_reasoning": review.get("reasoning", ""),
            "quality_score": review.get("quality_score", 70),
            "concerns": review.get("concerns", []),
            "recommendations": review.get("recommendations", []),
            "escalation_path": review.get("escalation_path") if review.get("decision") == "escalate" else None,
        }
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=review.get("confidence", 0.85),
            provenance=[{
                "source": "llm_quality_review",
                "trigger_reason": trigger_reason,
            }],
            metadata={"model": self.config.model},
        )
    
    async def _perform_quality_review(
        self,
        ticker: str,
        previous_phases: Dict,
        confidence_score: Dict,
        risk_score: Dict,
        trigger_reason: str,
    ) -> Dict[str, Any]:
        """Perform quality review using LLM.
        
        Args:
            ticker: Stock ticker
            previous_phases: All phase outputs
            confidence_score: Confidence score
            risk_score: Risk score
            trigger_reason: Reason for trigger
            
        Returns:
            Quality review results
        """
        variables = {
            "ticker": ticker,
            "full_analysis": json.dumps(previous_phases, indent=2, default=str),
            "verification_results": json.dumps(previous_phases.get("VERIFIER", {}), indent=2, default=str),
            "confidence_score": json.dumps(confidence_score, indent=2, default=str),
            "risk_assessment": json.dumps(risk_score, indent=2, default=str),
            "trigger_reason": trigger_reason,
        }
        
        system_prompt = self.prompt_loader.load_prompt("qualityguardian", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "qualityguardian",
            "quality_review.txt",
            variables,
        )
        
        request = LLMRequest(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout_seconds=self.config.timeout_seconds,
        )
        
        try:
            response = await self.llm_client.complete(request)
            
            try:
                result = json.loads(response.content)
                review = result.get("quality_review", {})
                return {
                    "decision": review.get("decision", "escalate"),
                    "reasoning": review.get("decision_reasoning", ""),
                    "quality_score": review.get("quality_score", 70),
                    "concerns": review.get("concerns", []),
                    "recommendations": review.get("recommendations", []),
                    "escalation_path": review.get("escalation_path"),
                    "confidence": review.get("confidence", 0.85),
                }
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                review = result.get("quality_review", {})
                return {
                    "decision": review.get("decision", "escalate"),
                    "reasoning": review.get("decision_reasoning", ""),
                    "quality_score": review.get("quality_score", 70),
                    "concerns": review.get("concerns", []),
                    "recommendations": review.get("recommendations", []),
                    "escalation_path": review.get("escalation_path"),
                    "confidence": review.get("confidence", 0.85),
                }
                
        except Exception as e:
            logger.error(f"Quality review failed: {e}")
            return self._fallback_review(confidence_score, risk_score)
    
    def _fallback_review(
        self,
        confidence_score: Dict,
        risk_score: Dict,
    ) -> Dict[str, Any]:
        """Fallback quality review.
        
        Args:
            confidence_score: Confidence score
            risk_score: Risk score
            
        Returns:
            Fallback review
        """
        overall_confidence = confidence_score.get("overall", 0.85)
        overall_risk = risk_score.get("overall", 50)
        
        # Auto-approve if confidence is high and risk is low
        if overall_confidence >= 0.85 and overall_risk <= 50:
            return {
                "decision": "approve",
                "reasoning": "Confidence and risk metrics within acceptable thresholds",
                "quality_score": 85,
                "concerns": [],
                "recommendations": ["Proceed with recommendation"],
                "escalation_path": None,
                "confidence": 0.85,
            }
        # Auto-reject if confidence is very low or risk is very high
        elif overall_confidence < 0.70 or overall_risk > 75:
            return {
                "decision": "reject",
                "reasoning": f"Confidence {overall_confidence:.0%} or risk {overall_risk} outside acceptable range",
                "quality_score": 60,
                "concerns": ["Low confidence or high risk detected"],
                "recommendations": ["Re-run analysis with additional data"],
                "escalation_path": None,
                "confidence": 0.75,
            }
        # Escalate for borderline cases
        else:
            return {
                "decision": "escalate",
                "reasoning": "Borderline metrics require human review",
                "quality_score": 75,
                "concerns": ["Confidence or risk near threshold"],
                "recommendations": ["Human review recommended"],
                "escalation_path": "Senior analyst review",
                "confidence": 0.80,
            }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate quality guardian output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        if "review_decision" not in data:
            logger.error("Missing review_decision in output")
            return False
        
        decision = data["review_decision"]
        if decision not in ["approve", "reject", "escalate"]:
            logger.error(f"Invalid decision: {decision}")
            return False
        
        if "decision_reasoning" not in data:
            logger.error("Missing decision_reasoning in output")
            return False
        
        if "quality_score" not in data:
            logger.error("Missing quality_score in output")
            return False
        
        return True
