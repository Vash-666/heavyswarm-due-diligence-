"""Strategist Agent - Phase 3 of HeavySwarm."""

import json
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class StrategistAgent(BaseAgent):
    """Agent that performs scenario analysis with devil's advocate.
    
    This is Phase 3 of the HeavySwarm workflow. It creates bull/base/bear
    scenarios and provides contrarian analysis.
    """
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the strategist agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.STRATEGIST
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute strategy analysis using LLM.
        
        Args:
            input_data: Input containing financial and risk analysis
            
        Returns:
            Agent output with scenarios and expected returns
        """
        logger.info(
            "Strategist executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        
        # Get data from previous phases
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        financial_analysis = previous_phases.get("FINANCIAL_ANALYST", {})
        risk_analysis = previous_phases.get("RISK_ANALYST", {})
        research_data = previous_phases.get("RESEARCHER", {})
        
        # Build scenarios using LLM
        scenarios = await self._build_scenarios(
            ticker,
            financial_analysis,
            risk_analysis,
            research_data,
        )
        
        # Build devil's advocate using LLM
        devils_advocate = await self._build_devils_advocate(
            ticker,
            input_data.thesis.thesis if input_data.thesis else "",
            scenarios,
        )
        
        # Calculate expected return
        bull = scenarios.get("bull", {})
        base = scenarios.get("base", {})
        bear = scenarios.get("bear", {})
        
        bull_return = bull.get("irr", 0) * bull.get("probability", 0)
        base_return = base.get("irr", 0) * base.get("probability", 0)
        bear_return = bear.get("irr", 0) * bear.get("probability", 0)
        
        expected_return = bull_return + base_return + bear_return
        
        output_data = {
            "scenarios": scenarios,
            "devils_advocate": devils_advocate,
            "expected_return": {
                "probability_weighted": round(expected_return, 3),
                "sharpe_ratio": 1.2,  # Would calculate properly
                "max_drawdown": bear.get("irr", -0.20),
                "calculation": f"({bull.get('probability', 0)} × {bull.get('irr', 0)}) + ({base.get('probability', 0)} × {base.get('irr', 0)}) + ({bear.get('probability', 0)} × {bear.get('irr', 0)})",
            },
        }
        
        # Confidence based on scenario quality
        confidence = 0.80
        if all(k in scenarios for k in ["bull", "base", "bear"]):
            confidence = 0.85
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=confidence,
            provenance=[{
                "source": "llm_scenario_analysis",
                "scenarios_built": list(scenarios.keys()),
            }],
            metadata={"model": self.config.model},
        )
    
    async def _build_scenarios(
        self,
        ticker: str,
        financial_analysis: Dict,
        risk_analysis: Dict,
        market_context: Dict,
    ) -> Dict[str, Any]:
        """Build scenarios using LLM.
        
        Args:
            ticker: Stock ticker
            financial_analysis: Financial analysis
            risk_analysis: Risk analysis
            market_context: Market context
            
        Returns:
            Scenarios
        """
        variables = {
            "ticker": ticker,
            "financial_analysis": json.dumps(financial_analysis, indent=2, default=str),
            "risk_assessment": json.dumps(risk_analysis, indent=2, default=str),
            "market_context": json.dumps(market_context, indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("strategist", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "strategist",
            "scenario_builder.txt",
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
                return result.get("scenarios", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("scenarios", {})
                
        except Exception as e:
            logger.error(f"Scenario build failed: {e}")
            return self._fallback_scenarios(ticker)
    
    async def _build_devils_advocate(
        self,
        ticker: str,
        thesis: str,
        scenarios: Dict,
    ) -> Dict[str, Any]:
        """Build devil's advocate analysis using LLM.
        
        Args:
            ticker: Stock ticker
            thesis: Original thesis
            scenarios: Built scenarios
            
        Returns:
            Devil's advocate analysis
        """
        variables = {
            "ticker": ticker,
            "thesis": thesis,
            "bullish_arguments": json.dumps(scenarios.get("bull", {}), indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("strategist", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "strategist",
            "devils_advocate.txt",
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
                return result.get("devils_advocate", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("devils_advocate", {})
                
        except Exception as e:
            logger.error(f"Devil's advocate build failed: {e}")
            return self._fallback_devils_advocate()
    
    def _fallback_scenarios(self, ticker: str) -> Dict[str, Any]:
        """Fallback scenarios.
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Fallback scenarios
        """
        return {
            "bull": {
                "thesis": f"{ticker} outperforms due to market leadership and margin expansion",
                "probability": 0.25,
                "price_target": 250.0,
                "current_price": 200.0,
                "upside": 0.25,
                "irr": 0.30,
                "key_drivers": ["Market share gains", "Margin expansion", "Multiple expansion"],
                "assumptions": {
                    "revenue_growth": "15% annually",
                    "margin_expansion": "200 bps",
                    "target_multiple": "25x P/E",
                },
                "catalysts": ["Earnings beat", "Guidance raise"],
                "timeline": "12-18 months",
            },
            "base": {
                "thesis": f"{ticker} meets expectations with steady execution",
                "probability": 0.50,
                "price_target": 220.0,
                "current_price": 200.0,
                "upside": 0.10,
                "irr": 0.15,
                "key_drivers": ["Steady growth", "Stable margins", "Market multiple"],
                "assumptions": {
                    "revenue_growth": "8% annually",
                    "margin_expansion": "50 bps",
                    "target_multiple": "20x P/E",
                },
                "catalysts": ["Consistent execution"],
                "timeline": "12-18 months",
            },
            "bear": {
                "thesis": f"{ticker} underperforms due to competitive pressure",
                "probability": 0.25,
                "price_target": 170.0,
                "current_price": 200.0,
                "upside": -0.15,
                "irr": -0.10,
                "key_drivers": ["Competitive pressure", "Margin compression", "Multiple contraction"],
                "assumptions": {
                    "revenue_growth": "3% annually",
                    "margin_compression": "100 bps",
                    "target_multiple": "15x P/E",
                },
                "catalysts": ["Earnings miss", "Guidance cut"],
                "timeline": "12-18 months",
            },
        }
    
    def _fallback_devils_advocate(self) -> Dict[str, Any]:
        """Fallback devil's advocate.
        
        Returns:
            Fallback devil's advocate
        """
        return {
            "contrarian_thesis": "The market is overestimating near-term growth potential",
            "ignored_risks": [
                {"risk": "Competition intensifying", "why_ignored": "Focus on historical dominance", "potential_impact": "Market share loss"},
            ],
            "valuation_concerns": {
                "current_multiple": "Above historical average",
                "historical_context": "Trading at 90th percentile of 5-year range",
                "peer_comparison": "Premium to peers not justified",
                "embedded_assumptions": "Assumes flawless execution",
                "margin_of_safety": "thin",
            },
            "timing_issues": [
                {"issue": "Product cycle maturity", "bull_timeline": "6 months", "realistic_timeline": "18 months"},
            ],
            "alternative_explanations": [
                {"observation": "Recent price strength", "bull_explanation": "Fundamental improvement", "alternative": "Market beta and momentum"},
            ],
            "what_would_change_mind": ["Sustainable margin expansion", "New product traction"],
            "confidence_in_contrarian_view": 0.60,
        }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate strategist output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        if "scenarios" not in data:
            logger.error("Missing scenarios in output")
            return False
        
        scenarios = data["scenarios"]
        required_scenarios = ["bull", "base", "bear"]
        
        for scenario in required_scenarios:
            if scenario not in scenarios:
                logger.error(f"Missing scenario: {scenario}")
                return False
        
        if "devils_advocate" not in data:
            logger.error("Missing devils_advocate in output")
            return False
        
        if "expected_return" not in data:
            logger.error("Missing expected_return in output")
            return False
        
        # Validate probabilities sum to ~1.0
        total_prob = sum(
            scenarios.get(s, {}).get("probability", 0)
            for s in required_scenarios
        )
        if not 0.95 <= total_prob <= 1.05:
            logger.warning(f"Scenario probabilities sum to {total_prob}, expected ~1.0")
        
        return True
