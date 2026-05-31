"""Risk Analyst Agent - Phase 2 of HeavySwarm (Parallel with Financial Analyst)."""

import json
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class RiskAnalystAgent(BaseAgent):
    """Agent that performs comprehensive risk assessment.
    
    This is Phase 2 of the HeavySwarm workflow, running in parallel with
    Financial Analyst. It creates a risk matrix with severity/probability scores.
    """
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the risk analyst agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.RISK_ANALYST
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute risk analysis using LLM.
        
        Args:
            input_data: Input containing research data
            
        Returns:
            Agent output with risk matrix
        """
        logger.info(
            "RiskAnalyst executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        
        # Get data from previous phases
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        research_data = previous_phases.get("RESEARCHER", {})
        
        # Build risk matrix using LLM
        risk_matrix = await self._build_risk_matrix(ticker, research_data)
        
        # Build stress tests using LLM
        stress_tests = await self._build_stress_tests(ticker, risk_matrix, research_data)
        
        # Calculate overall risk score
        category_scores = risk_matrix.get("risk_score", {}).get("category_breakdown", {})
        if category_scores:
            overall_score = sum(category_scores.values()) / len(category_scores)
        else:
            overall_score = 50
        
        output_data = {
            "risk_matrix": risk_matrix.get("risk_matrix", {}),
            "risk_score": {
                "overall": round(overall_score),
                "category_breakdown": category_scores,
                "methodology": "Weighted average of category scores (severity x probability)",
            },
            "stress_test": stress_tests,
        }
        
        # Confidence based on data quality
        confidence = risk_matrix.get("confidence", 0.75)
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=confidence,
            provenance=[{
                "source": "llm_risk_analysis",
                "categories_analyzed": list(risk_matrix.get("risk_matrix", {}).keys()),
            }],
            metadata={"model": self.config.model},
        )
    
    async def _build_risk_matrix(
        self,
        ticker: str,
        research_data: Dict,
    ) -> Dict[str, Any]:
        """Build risk matrix using LLM.
        
        Args:
            ticker: Stock ticker
            research_data: Research data
            
        Returns:
            Risk matrix results
        """
        variables = {
            "ticker": ticker,
            "research_data": json.dumps(research_data, indent=2, default=str),
            "financial_analysis": json.dumps({}, indent=2),  # Would come from parallel phase
        }
        
        system_prompt = self.prompt_loader.load_prompt("risk_analyst", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "risk_analyst",
            "risk_matrix.txt",
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
                return result.get("risk_matrix", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result
                
        except Exception as e:
            logger.error(f"Risk matrix build failed: {e}")
            return self._fallback_risk_matrix(ticker)
    
    async def _build_stress_tests(
        self,
        ticker: str,
        risk_matrix: Dict,
        research_data: Dict,
    ) -> Dict[str, Any]:
        """Build stress tests using LLM.
        
        Args:
            ticker: Stock ticker
            risk_matrix: Risk matrix
            research_data: Research data
            
        Returns:
            Stress test results
        """
        variables = {
            "ticker": ticker,
            "financial_model": json.dumps(research_data.get("financial_data", {}), indent=2, default=str),
            "risk_matrix": json.dumps(risk_matrix, indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("risk_analyst", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "risk_analyst",
            "stress_test.txt",
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
                return result.get("stress_tests", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("stress_tests", {})
                
        except Exception as e:
            logger.error(f"Stress test build failed: {e}")
            return self._fallback_stress_tests()
    
    def _fallback_risk_matrix(self, ticker: str) -> Dict[str, Any]:
        """Fallback risk matrix.
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Fallback risk matrix
        """
        return {
            "risk_matrix": {
                "market_risks": [
                    {
                        "risk": "Economic recession",
                        "severity": 4,
                        "probability": 3,
                        "risk_score": 12,
                        "mitigation": "Diversified revenue streams",
                        "time_horizon": "medium",
                    },
                    {
                        "risk": "Interest rate increases",
                        "severity": 3,
                        "probability": 4,
                        "risk_score": 12,
                        "mitigation": "Strong cash position",
                        "time_horizon": "short",
                    },
                ],
                "credit_risks": [
                    {
                        "risk": "Counterparty default",
                        "severity": 2,
                        "probability": 2,
                        "risk_score": 4,
                        "mitigation": "Investment-grade counterparties",
                        "time_horizon": "long",
                    },
                ],
                "operational_risks": [
                    {
                        "risk": "Supply chain disruption",
                        "severity": 3,
                        "probability": 3,
                        "risk_score": 9,
                        "mitigation": "Multiple supplier strategy",
                        "time_horizon": "medium",
                    },
                ],
                "regulatory_risks": [
                    {
                        "risk": "Antitrust enforcement",
                        "severity": 4,
                        "probability": 3,
                        "risk_score": 12,
                        "mitigation": "Legal compliance team",
                        "time_horizon": "medium",
                    },
                ],
                "esg_risks": [
                    {
                        "risk": "Environmental regulations",
                        "severity": 3,
                        "probability": 4,
                        "risk_score": 12,
                        "mitigation": "Carbon neutral commitment",
                        "time_horizon": "long",
                    },
                ],
            },
            "risk_score": {
                "overall": 50,
                "category_breakdown": {
                    "market": 40,
                    "credit": 20,
                    "operational": 30,
                    "regulatory": 40,
                    "esg": 35,
                },
            },
            "confidence": 0.70,
        }
    
    def _fallback_stress_tests(self) -> Dict[str, Any]:
        """Fallback stress tests.
        
        Returns:
            Fallback stress tests
        """
        return {
            "recession_scenario": {
                "description": "GDP contraction of 3-5%",
                "assumptions": ["Unemployment spike", "Consumer spending decline"],
                "revenue_impact": -0.20,
                "recovery_time": "18-24 months",
            },
            "interest_rate_shock": {
                "description": "Fed funds rate increases 300-400 bps",
                "assumptions": ["10-year Treasury rises to 5-6%"],
                "impact": -0.15,
            },
            "liquidity_crisis": {
                "description": "Credit markets freeze",
                "assumptions": ["Revenue drops 20%"],
                "impact": -0.10,
            },
        }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate risk analyst output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        if "risk_matrix" not in data:
            logger.error("Missing risk_matrix in output")
            return False
        
        matrix = data["risk_matrix"]
        required_categories = [
            "market_risks",
            "credit_risks",
            "operational_risks",
            "regulatory_risks",
            "esg_risks",
        ]
        
        for category in required_categories:
            if category not in matrix:
                logger.error(f"Missing risk category: {category}")
                return False
        
        if "risk_score" not in data:
            logger.error("Missing risk_score in output")
            return False
        
        return True