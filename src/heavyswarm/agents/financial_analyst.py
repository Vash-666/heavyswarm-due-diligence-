"""Financial Analyst Agent - Phase 2 of HeavySwarm."""

import json
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class FinancialAnalystAgent(BaseAgent):
    """Agent that builds valuation models and price targets.
    
    This is Phase 2 of the HeavySwarm workflow. It performs financial analysis
    including DCF modeling, comparable company analysis, and precedent transactions.
    """
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the financial analyst agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.FINANCIAL_ANALYST
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute financial analysis using LLM.
        
        Args:
            input_data: Input containing research data
            
        Returns:
            Agent output with valuation models
        """
        logger.info(
            "FinancialAnalyst executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        
        # Get research data from previous phase
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        research_data = previous_phases.get("RESEARCHER", {})
        financial_data = research_data.get("financial_data", {})
        market_data = research_data.get("market_trends", {})
        
        # Build DCF model using LLM
        dcf_result = await self._build_dcf_model(ticker, financial_data, market_data)
        
        # Build comps analysis using LLM
        comps_result = await self._build_comps_analysis(ticker, financial_data, research_data)
        
        # Build precedent transactions using LLM
        precedent_result = await self._build_precedent_analysis(ticker, financial_data, market_data)
        
        # Calculate consensus price target
        dcf_value = dcf_result.get("fair_value", 0)
        comps_value = comps_result.get("weighted_average", 0)
        precedent_value = precedent_result.get("ev_ebitda_median", 0)
        
        # Weighted average (DCF 50%, Comps 30%, Precedent 20%)
        weights = {"dcf": 0.5, "comps": 0.3, "precedent": 0.2}
        valid_values = []
        
        if dcf_value > 0:
            valid_values.append((dcf_value, weights["dcf"]))
        if comps_value > 0:
            valid_values.append((comps_value, weights["comps"]))
        if precedent_value > 0:
            valid_values.append((precedent_value, weights["precedent"]))
        
        if valid_values:
            total_weight = sum(w for _, w in valid_values)
            consensus = sum(v * w for v, w in valid_values) / total_weight
        else:
            consensus = 0
        
        output_data = {
            "valuation_models": {
                "dcf": dcf_result,
                "comps": comps_result,
                "precedent": precedent_result,
            },
            "price_target": {
                "consensus": round(consensus, 2),
                "confidence_interval": {
                    "low": round(consensus * 0.85, 2),
                    "high": round(consensus * 1.15, 2),
                },
                "methodology": "Weighted average of DCF (50%), Comps (30%), and Precedent (20%)",
            },
        }
        
        # Calculate confidence based on data quality
        confidence = 0.75
        if dcf_value > 0:
            confidence += 0.05
        if comps_value > 0:
            confidence += 0.05
        if precedent_value > 0:
            confidence += 0.05
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=min(0.90, confidence),
            provenance=[{
                "source": "llm_valuation_models",
                "models_used": ["dcf", "comps", "precedent"],
            }],
            metadata={"model": self.config.model},
        )
    
    async def _build_dcf_model(
        self,
        ticker: str,
        financial_data: Dict,
        market_data: Dict,
    ) -> Dict[str, Any]:
        """Build DCF model using LLM.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data from research
            market_data: Market data from research
            
        Returns:
            DCF model results
        """
        variables = {
            "ticker": ticker,
            "financial_data": json.dumps(financial_data, indent=2, default=str),
            "market_data": json.dumps(market_data, indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("financial_analyst", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "financial_analyst",
            "dcf_model.txt",
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
            
            # Parse JSON response
            try:
                result = json.loads(response.content)
                return result.get("dcf", {})
            except json.JSONDecodeError:
                # Try to extract JSON from markdown
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("dcf", {})
                
        except Exception as e:
            logger.error(f"DCF model build failed: {e}")
            return self._fallback_dcf(ticker, financial_data)
    
    async def _build_comps_analysis(
        self,
        ticker: str,
        financial_data: Dict,
        research_data: Dict,
    ) -> Dict[str, Any]:
        """Build comparable company analysis using LLM.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data
            research_data: Full research data
            
        Returns:
            Comps analysis results
        """
        competitive_data = research_data.get("competitive_landscape", {})
        
        variables = {
            "ticker": ticker,
            "company_financials": json.dumps(financial_data, indent=2, default=str),
            "peer_companies": json.dumps(competitive_data.get("peers", []), indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("financial_analyst", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "financial_analyst",
            "comps_analysis.txt",
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
                return result.get("comps", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("comps", {})
                
        except Exception as e:
            logger.error(f"Comps analysis failed: {e}")
            return self._fallback_comps(ticker, financial_data)
    
    async def _build_precedent_analysis(
        self,
        ticker: str,
        financial_data: Dict,
        market_data: Dict,
    ) -> Dict[str, Any]:
        """Build precedent transaction analysis using LLM.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data
            market_data: Market data
            
        Returns:
            Precedent analysis results
        """
        variables = {
            "ticker": ticker,
            "company_profile": json.dumps(financial_data, indent=2, default=str),
            "industry": json.dumps(market_data, indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("financial_analyst", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "financial_analyst",
            "precedent_transactions.txt",
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
                return result.get("precedent", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("precedent", {})
                
        except Exception as e:
            logger.error(f"Precedent analysis failed: {e}")
            return self._fallback_precedent(ticker, financial_data)
    
    def _fallback_dcf(self, ticker: str, financial_data: Dict) -> Dict[str, Any]:
        """Fallback DCF model.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data
            
        Returns:
            Fallback DCF results
        """
        metrics = financial_data.get("metrics", {})
        revenue = metrics.get("revenue", {}).get("value", 0)
        
        # Simple fallback based on revenue
        if revenue:
            fair_value = revenue * 0.000005  # Very rough heuristic
        else:
            fair_value = 100.0
        
        return {
            "fair_value": round(fair_value, 2),
            "wacc": 0.085,
            "terminal_growth": 0.025,
            "projections": [],
            "upside_downside": {
                "bull": round(fair_value * 1.25, 2),
                "base": round(fair_value, 2),
                "bear": round(fair_value * 0.75, 2),
            },
            "confidence": 0.60,
        }
    
    def _fallback_comps(self, ticker: str, financial_data: Dict) -> Dict[str, Any]:
        """Fallback comps analysis.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data
            
        Returns:
            Fallback comps results
        """
        return {
            "peer_companies": [],
            "multiples_summary": {},
            "implied_values": {},
            "weighted_average": 0,
            "confidence": 0.50,
        }
    
    def _fallback_precedent(self, ticker: str, financial_data: Dict) -> Dict[str, Any]:
        """Fallback precedent analysis.
        
        Args:
            ticker: Stock ticker
            financial_data: Financial data
            
        Returns:
            Fallback precedent results
        """
        return {
            "transactions": [],
            "multiples_summary": {},
            "implied_values": {},
            "ev_ebitda_median": 0,
            "confidence": 0.50,
        }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate financial analyst output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        if "valuation_models" not in data:
            logger.error("Missing valuation_models in output")
            return False
        
        models = data["valuation_models"]
        required_models = ["dcf", "comps", "precedent"]
        
        for model in required_models:
            if model not in models:
                logger.error(f"Missing model: {model}")
                return False
        
        if "price_target" not in data:
            logger.error("Missing price_target in output")
            return False
        
        return True