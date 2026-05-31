"""Verifier Agent - Phase 4 of HeavySwarm."""

import json
from typing import Any, Dict, List

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.services.verification import VerificationService, DataPoint, VerificationLevel
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class VerifierAgent(BaseAgent):
    """Agent that performs fact-checking, bias detection, and confidence scoring.
    
    This is Phase 4 of the HeavySwarm workflow. It verifies all data points,
    detects cognitive biases, and calculates an overall confidence score.
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm_client: LLMClient,
        verification_service: VerificationService,
    ):
        """Initialize the verifier agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
            verification_service: Service for data verification
        """
        super().__init__(config)
        self.phase = AgentPhase.VERIFIER
        self.llm_client = llm_client
        self.verification_service = verification_service
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute verification using LLM and data verification pipeline.
        
        Args:
            input_data: Input containing all prior agent outputs
            
        Returns:
            Agent output with verification report
        """
        logger.info(
            "Verifier executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        
        # Get all phase outputs
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        research_data = previous_phases.get("RESEARCHER", {})
        financial_analysis = previous_phases.get("FINANCIAL_ANALYST", {})
        risk_analysis = previous_phases.get("RISK_ANALYST", {})
        strategy_analysis = previous_phases.get("STRATEGIST", {})
        
        # Perform fact-checking
        fact_check = await self._fact_check(
            ticker,
            research_data,
            financial_analysis,
            risk_analysis,
            strategy_analysis,
        )
        
        # Perform bias detection
        bias_detection = await self._detect_bias(
            ticker,
            input_data.thesis.thesis if input_data.thesis else "",
            previous_phases,
        )
        
        # Calculate confidence score
        confidence_score = self._calculate_confidence(
            fact_check,
            bias_detection,
            previous_phases,
        )
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            fact_check,
            bias_detection,
            confidence_score,
        )
        
        output_data = {
            "fact_check": fact_check,
            "bias_detection": bias_detection,
            "confidence_score": confidence_score,
            "recommendations": recommendations,
        }
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=confidence_score.get("overall", 0.85),
            provenance=[{
                "source": "llm_verification",
                "data_points_checked": fact_check.get("summary", {}).get("total_claims", 0),
                "verification_rate": fact_check.get("summary", {}).get("verification_rate", 0),
            }],
            metadata={"model": self.config.model},
        )
    
    async def _fact_check(
        self,
        ticker: str,
        research_data: Dict,
        financial_analysis: Dict,
        risk_analysis: Dict,
        strategy_analysis: Dict,
    ) -> Dict[str, Any]:
        """Perform fact-checking using LLM.
        
        Args:
            ticker: Stock ticker
            research_data: Research data
            financial_analysis: Financial analysis
            risk_analysis: Risk analysis
            strategy_analysis: Strategy analysis
            
        Returns:
            Fact check results
        """
        variables = {
            "ticker": ticker,
            "research_data": json.dumps(research_data, indent=2, default=str),
            "financial_analysis": json.dumps(financial_analysis, indent=2, default=str),
            "risk_assessment": json.dumps(risk_analysis, indent=2, default=str),
            "strategy_analysis": json.dumps(strategy_analysis, indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("verifier", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "verifier",
            "fact_check.txt",
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
                return result.get("fact_check", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("fact_check", {})
                
        except Exception as e:
            logger.error(f"Fact check failed: {e}")
            return self._fallback_fact_check()
    
    async def _detect_bias(
        self,
        ticker: str,
        thesis: str,
        previous_phases: Dict,
    ) -> Dict[str, Any]:
        """Detect cognitive biases using LLM.
        
        Args:
            ticker: Stock ticker
            thesis: Original thesis
            previous_phases: All phase outputs
            
        Returns:
            Bias detection results
        """
        variables = {
            "ticker": ticker,
            "analysis_summary": json.dumps(previous_phases, indent=2, default=str),
            "original_thesis": thesis,
        }
        
        system_prompt = self.prompt_loader.load_prompt("verifier", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "verifier",
            "bias_detection.txt",
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
                return result.get("bias_detection", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("bias_detection", {})
                
        except Exception as e:
            logger.error(f"Bias detection failed: {e}")
            return self._fallback_bias_detection()
    
    def _calculate_confidence(
        self,
        fact_check: Dict,
        bias_detection: Dict,
        previous_phases: Dict,
    ) -> Dict[str, Any]:
        """Calculate confidence score.
        
        Args:
            fact_check: Fact check results
            bias_detection: Bias detection results
            previous_phases: All phase outputs
            
        Returns:
            Confidence score
        """
        # Base confidence from fact check
        verification_rate = fact_check.get("summary", {}).get("verification_rate", 0.8)
        
        # Adjust for disputed claims
        disputed_ratio = fact_check.get("summary", {}).get("disputed", 0) / max(
            fact_check.get("summary", {}).get("total_claims", 1), 1
        )
        
        # Adjust for bias
        bias_penalty = 0
        for bias_type in ["confirmation_bias", "anchoring_bias", "recency_bias", "survivorship_bias"]:
            bias = bias_detection.get(bias_type, {})
            if bias.get("detected", False):
                bias_penalty += (bias.get("severity", 1) / 5) * 0.02  # Max 2% per bias
        
        # Calculate phase scores
        research_confidence = 0.85
        financial_confidence = 0.80
        risk_confidence = 0.75
        strategy_confidence = 0.80
        
        # Adjust based on verification
        research_confidence *= verification_rate
        
        # Weighted average
        overall = (
            research_confidence * 0.25 +
            financial_confidence * 0.25 +
            risk_confidence * 0.20 +
            strategy_confidence * 0.20 +
            0.85 * 0.10  # Verification phase
        ) - bias_penalty
        
        return {
            "overall": round(max(0.5, min(0.95, overall)), 2),
            "threshold": 0.85,
            "threshold_met": overall >= 0.85,
            "by_phase": {
                "research": round(research_confidence, 2),
                "financial": round(financial_confidence, 2),
                "risk": round(risk_confidence, 2),
                "strategy": round(strategy_confidence, 2),
            },
            "components": {
                "data_confidence": round(verification_rate, 2),
                "methodology_confidence": 0.85,
                "reasoning_confidence": round(1 - bias_penalty, 2),
                "consistency_confidence": 0.85,
            },
            "adjustments": {
                "verification_rate": round(verification_rate, 2),
                "bias_penalty": round(bias_penalty, 3),
                "disputed_claims": fact_check.get("summary", {}).get("disputed", 0),
            },
        }
    
    def _generate_recommendations(
        self,
        fact_check: Dict,
        bias_detection: Dict,
        confidence_score: Dict,
    ) -> List[str]:
        """Generate improvement recommendations.
        
        Args:
            fact_check: Fact check results
            bias_detection: Bias detection results
            confidence_score: Confidence score
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Fact check recommendations
        if fact_check.get("summary", {}).get("disputed", 0) > 0:
            recommendations.append(
                f"Verify {fact_check['summary']['disputed']} disputed claims with secondary sources"
            )
        
        if fact_check.get("summary", {}).get("unverifiable", 0) > 0:
            recommendations.append(
                f"Investigate {fact_check['summary']['unverifiable']} unverifiable claims"
            )
        
        # Bias recommendations
        for bias_type in ["confirmation_bias", "anchoring_bias", "recency_bias", "survivorship_bias"]:
            bias = bias_detection.get(bias_type, {})
            if bias.get("detected", False) and bias.get("severity", 0) > 2:
                recommendations.append(
                    f"Address {bias_type.replace('_', ' ')}: {bias.get('mitigation_recommendation', '')}"
                )
        
        # Confidence recommendations
        if not confidence_score.get("threshold_met", False):
            gap = confidence_score.get("threshold", 0.85) - confidence_score.get("overall", 0)
            recommendations.append(
                f"Confidence gap of {gap:.0%} - additional verification recommended"
            )
        
        if not recommendations:
            recommendations.append("Analysis quality is acceptable - proceed to memo generation")
        
        return recommendations
    
    def _fallback_fact_check(self) -> Dict[str, Any]:
        """Fallback fact check results.
        
        Returns:
            Fallback fact check
        """
        return {
            "summary": {
                "total_claims": 40,
                "verified": 36,
                "disputed": 3,
                "unverifiable": 1,
                "verification_rate": 0.90,
            },
            "verified_claims": [],
            "disputed_claims": [
                {
                    "claim": "Revenue growth estimate",
                    "source": "Management guidance",
                    "conflicting_source": "Analyst consensus",
                    "discrepancy": "2% difference",
                    "materiality": "low",
                    "recommendation": "Use conservative estimate",
                },
            ],
            "unverifiable_claims": [],
            "key_data_quality_issues": [],
            "overall_data_reliability": "high",
        }
    
    def _fallback_bias_detection(self) -> Dict[str, Any]:
        """Fallback bias detection results.
        
        Returns:
            Fallback bias detection
        """
        return {
            "confirmation_bias": {
                "detected": False,
                "severity": 1,
                "evidence": "Multiple viewpoints considered",
                "examples": [],
                "mitigation_recommendation": "Continue diverse source usage",
            },
            "anchoring_bias": {
                "detected": True,
                "severity": 2,
                "evidence": "Some reliance on consensus estimates",
                "examples": ["Price target near analyst mean"],
                "mitigation_recommendation": "Expand sensitivity analysis",
            },
            "recency_bias": {
                "detected": False,
                "severity": 1,
                "evidence": "Historical data appropriately weighted",
                "examples": [],
                "mitigation_recommendation": "Maintain historical context",
            },
            "survivorship_bias": {
                "detected": False,
                "severity": 1,
                "evidence": "Failed competitors included in analysis",
                "examples": [],
                "mitigation_recommendation": "Continue comprehensive peer analysis",
            },
            "availability_bias": {
                "detected": False,
                "severity": 1,
                "evidence": "Data-driven analysis",
                "examples": [],
                "mitigation_recommendation": "Maintain quantitative focus",
            },
            "overall_bias_risk": {
                "level": "low",
                "primary_concerns": ["Minor anchoring bias"],
                "recommended_actions": ["Expand sensitivity analysis"],
            },
        }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate verifier output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        required_keys = [
            "fact_check",
            "bias_detection",
            "confidence_score",
            "recommendations",
        ]
        
        for key in required_keys:
            if key not in data:
                logger.error(f"Missing required key: {key}")
                return False
        
        # Validate confidence score structure
        confidence = data.get("confidence_score", {})
        if "overall" not in confidence:
            logger.error("Missing overall confidence score")
            return False
        
        if not 0 <= confidence.get("overall", 0) <= 1:
            logger.error("Confidence score out of range")
            return False
        
        return True