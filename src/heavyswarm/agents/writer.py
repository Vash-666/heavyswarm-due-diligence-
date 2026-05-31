"""Writer Agent - Phase 5 of HeavySwarm."""

import json
from datetime import datetime
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase, Recommendation, RiskRating, SignalAction
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class WriterAgent(BaseAgent):
    """Agent that generates the investment memo and trading signal.
    
    This is Phase 5 of the HeavySwarm workflow. It synthesizes all prior
    analysis into a structured investment memo and trading signal.
    """
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the writer agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.WRITER
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute memo writing using LLM.
        
        Args:
            input_data: Input containing all verified analysis
            
        Returns:
            Agent output with investment memo and trading signal
        """
        logger.info(
            "Writer executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        ticker = input_data.thesis.ticker if input_data.thesis else "UNKNOWN"
        thesis = input_data.thesis
        
        # Get all phase outputs
        context = input_data.context
        previous_phases = context.get("previous_phases", {})
        
        # Generate memo using LLM
        memo = await self._generate_memo(ticker, thesis, previous_phases)
        
        # Generate trading signal
        trading_signal = self._generate_trading_signal(ticker, memo, previous_phases)
        
        output_data = {
            "memo": memo,
            "trading_signal": trading_signal,
        }
        
        # Confidence from verification phase
        verifier_output = previous_phases.get("VERIFIER", {})
        confidence = verifier_output.get("confidence_score", {}).get("overall", 0.85)
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=confidence,
            provenance=[{
                "source": "llm_memo_generation",
                "phases_synthesized": list(previous_phases.keys()),
            }],
            metadata={"model": self.config.model},
        )
    
    async def _generate_memo(
        self,
        ticker: str,
        thesis: Any,
        previous_phases: Dict,
    ) -> Dict[str, Any]:
        """Generate investment memo using LLM.
        
        Args:
            ticker: Stock ticker
            thesis: Investment thesis
            previous_phases: All phase outputs
            
        Returns:
            Investment memo
        """
        variables = {
            "ticker": ticker,
            "all_phase_outputs": json.dumps(previous_phases, indent=2, default=str),
            "verification_results": json.dumps(previous_phases.get("VERIFIER", {}), indent=2, default=str),
        }
        
        system_prompt = self.prompt_loader.load_prompt("writer", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "writer",
            "memo_template.txt",
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
                return result.get("memo", {})
            except json.JSONDecodeError:
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                result = json.loads(content.strip())
                return result.get("memo", {})
                
        except Exception as e:
            logger.error(f"Memo generation failed: {e}")
            return self._fallback_memo(ticker, thesis, previous_phases)
    
    def _generate_trading_signal(
        self,
        ticker: str,
        memo: Dict,
        previous_phases: Dict,
    ) -> Dict[str, Any]:
        """Generate trading signal.
        
        Args:
            ticker: Stock ticker
            memo: Investment memo
            previous_phases: All phase outputs
            
        Returns:
            Trading signal
        """
        # Extract key data
        executive_summary = memo.get("executive_summary", {})
        recommendation = executive_summary.get("recommendation", "hold")
        confidence = memo.get("metadata", {}).get("confidence_score", 0.85)
        
        # Get price targets
        price_target = executive_summary.get("price_target", {})
        base_target = price_target.get("base", 0)
        current_price = executive_summary.get("current_price", 0)
        
        # Determine action
        action_map = {
            "buy": "buy",
            "hold": "hold",
            "sell": "sell",
            "watch": "hold",
        }
        action = action_map.get(recommendation, "hold")
        
        # Determine urgency
        verifier_output = previous_phases.get("VERIFIER", {})
        confidence_score = verifier_output.get("confidence_score", {})
        
        if confidence_score.get("threshold_met", False) and action == "buy":
            urgency = "this_week"
        elif action == "sell":
            urgency = "immediate"
        else:
            urgency = "this_month"
        
        # Position sizing based on confidence and risk
        risk_rating = executive_summary.get("risk_rating", "medium")
        risk_multiplier = {
            "low": 1.0,
            "medium": 0.8,
            "high": 0.5,
            "very_high": 0.3,
        }.get(risk_rating, 0.8)
        
        base_position = 0.05  # 5% base
        position_size = base_position * confidence * risk_multiplier
        
        # Get scenarios for price targets
        strategist_output = previous_phases.get("STRATEGIST", {})
        scenarios = strategist_output.get("scenarios", {})
        
        return {
            "signal_id": f"{ticker}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.utcnow().isoformat(),
            "ticker": ticker,
            "action": action,
            "confidence": confidence,
            "urgency": urgency,
            "position_sizing": {
                "recommended_pct": round(position_size, 3),
                "max_pct": round(position_size * 1.5, 3),
                "rationale": f"Base 5% × confidence {confidence:.0%} × risk factor {risk_multiplier}",
            },
            "price_targets": {
                "current": current_price,
                "entry": current_price,
                "stop_loss": round(base_target * 0.80, 2) if base_target > 0 else round(current_price * 0.85, 2),
                "take_profit": [
                    round(base_target * 0.90, 2) if base_target > 0 else round(current_price * 1.10, 2),
                    base_target if base_target > 0 else round(current_price * 1.20, 2),
                    round(base_target * 1.15, 2) if base_target > 0 else round(current_price * 1.30, 2),
                ],
                "time_horizon_days": 365,
            },
            "risk_metrics": {
                "var_95": round(current_price * 0.05, 2) if current_price > 0 else 0,
                "max_drawdown": scenarios.get("bear", {}).get("irr", -0.20),
                "sharpe_ratio": 1.2,
                "risk_rating": risk_rating,
            },
            "execution": {
                "order_type": "limit" if action == "buy" else "market",
                "sizing_strategy": "scale_in" if confidence < 0.90 else "full",
                "exit_conditions": [
                    "Stop loss triggered",
                    "Thesis invalidated",
                    "Target price reached",
                ],
            },
            "monitoring": {
                "key_levels": [
                    round(current_price * 0.95, 2),
                    current_price,
                    round(base_target * 0.5, 2) if base_target > 0 else round(current_price * 1.10, 2),
                ],
                "catalyst_dates": [],
                "review_trigger": "Earnings or material event",
            },
            "audit": {
                "memo_reference": memo.get("metadata", {}).get("version", "1.0.0"),
                "confidence_score": confidence,
                "verification_rate": previous_phases.get("RESEARCHER", {}).get("provenance", {}).get("verification_rate", 0),
                "agents_involved": list(previous_phases.keys()),
            },
        }
    
    def _fallback_memo(
        self,
        ticker: str,
        thesis: Any,
        previous_phases: Dict,
    ) -> Dict[str, Any]:
        """Fallback memo generation.
        
        Args:
            ticker: Stock ticker
            thesis: Investment thesis
            previous_phases: All phase outputs
            
        Returns:
            Fallback memo
        """
        verifier_output = previous_phases.get("VERIFIER", {})
        confidence = verifier_output.get("confidence_score", {}).get("overall", 0.85)
        
        financial_analysis = previous_phases.get("FINANCIAL_ANALYST", {})
        price_target = financial_analysis.get("price_target", {}).get("consensus", 200)
        
        return {
            "metadata": {
                "ticker": ticker,
                "date": datetime.utcnow().isoformat(),
                "version": "1.0.0",
                "confidence_score": confidence,
            },
            "executive_summary": {
                "recommendation": "hold",
                "position_size": "3-5% of portfolio",
                "time_horizon": "12-18 months",
                "key_thesis": thesis.thesis if thesis else "Awaiting further analysis",
                "risk_rating": "medium",
                "price_target": {"base": price_target, "range": {"low": price_target * 0.85, "high": price_target * 1.15}},
            },
            "investment_thesis": "See detailed analysis in previous phases.",
            "valuation_analysis": "See financial analyst output.",
            "risk_assessment": "See risk analyst output.",
            "scenarios": "See strategist output.",
            "catalysts": [],
            "appendices": {
                "data_sources": ["Alpha Vantage", "SEC EDGAR", "News API"],
                "model_assumptions": ["See individual phase outputs"],
            },
        }
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate writer output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        if "memo" not in data:
            logger.error("Missing memo in output")
            return False
        
        memo = data["memo"]
        required_sections = [
            "metadata",
            "executive_summary",
            "investment_thesis",
            "valuation_analysis",
            "risk_assessment",
            "scenarios",
        ]
        
        for section in required_sections:
            if section not in memo:
                logger.error(f"Missing memo section: {section}")
                return False
        
        if "trading_signal" not in data:
            logger.error("Missing trading_signal in output")
            return False
        
        signal = data["trading_signal"]
        if "action" not in signal:
            logger.error("Missing action in trading signal")
            return False
        
        return True
