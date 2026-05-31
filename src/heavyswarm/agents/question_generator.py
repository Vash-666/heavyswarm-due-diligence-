"""Question Generator Agent - Phase 0 of HeavySwarm."""

import json
from typing import Any, Dict

from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput, BaseAgent
from heavyswarm.core.enums import AgentPhase
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.services.prompt_loader import PromptLoader
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class QuestionGeneratorAgent(BaseAgent):
    """Agent that decomposes investment thesis into specialized research prompts.
    
    This is Phase 0 of the HeavySwarm workflow. It takes a high-level investment
    thesis and breaks it down into 4 specialized research prompts for the
    parallel research phase.
    """
    
    def __init__(self, config: AgentConfig, llm_client: LLMClient):
        """Initialize the question generator agent.
        
        Args:
            config: Agent configuration
            llm_client: LLM client for making API calls
        """
        super().__init__(config)
        self.phase = AgentPhase.QUESTION_GENERATOR
        self.llm_client = llm_client
        self.prompt_loader = PromptLoader()
    
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute question generation using LLM.
        
        Args:
            input_data: Input containing the investment thesis
            
        Returns:
            Agent output with 4 specialized research prompts
        """
        logger.info(
            "QuestionGenerator executing",
            extra={
                "ticker": input_data.thesis.ticker if input_data.thesis else None,
            },
        )
        
        thesis = input_data.thesis
        
        # Prepare prompt variables
        variables = {
            "ticker": thesis.ticker if thesis else "UNKNOWN",
            "thesis": thesis.thesis if thesis else "",
            "time_horizon": thesis.time_horizon if thesis else "medium_term",
            "risk_tolerance": thesis.risk_tolerance if thesis else "moderate",
            "position_size": str(thesis.position_size * 100) if thesis else "0",
            "priority": thesis.priority if thesis else "medium",
        }
        
        # Load and render prompts
        system_prompt = self.prompt_loader.load_prompt("question_generator", "system.txt")
        user_prompt = self.prompt_loader.render_prompt(
            "question_generator",
            "decompose.txt",
            variables,
        )
        
        # Create LLM request
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
        
        # Call LLM
        try:
            response = await self.llm_client.complete(request)
            
            # Parse JSON response
            try:
                output_data = json.loads(response.content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM response as JSON: {e}")
                # Try to extract JSON from markdown code block
                content = response.content
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                output_data = json.loads(content.strip())
            
            # Extract confidence from metadata or use default
            metadata = output_data.get("metadata", {})
            confidence = metadata.get("decomposition_confidence", 0.90)
            
            return AgentOutput(
                phase=self.phase,
                data=output_data,
                confidence=confidence,
                provenance=[{
                    "source": "llm",
                    "model": response.model,
                    "response_time_ms": response.response_time_ms,
                }],
                processing_time_ms=response.response_time_ms,
                metadata={
                    "model": response.model,
                    "usage": response.usage,
                },
            )
            
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            # Fallback to template-based generation
            return await self._fallback_execute(input_data)
    
    async def _fallback_execute(self, input_data: AgentInput) -> AgentOutput:
        """Fallback execution without LLM.
        
        Args:
            input_data: Input containing the investment thesis
            
        Returns:
            Agent output with generated prompts
        """
        thesis = input_data.thesis
        ticker = thesis.ticker if thesis else "UNKNOWN"
        thesis_statement = thesis.thesis if thesis else ""
        time_horizon = thesis.time_horizon if thesis else "medium_term"
        
        # Adjust depth based on time horizon
        if time_horizon == "short_term":
            focus_period = "quarterly"
            metrics_focus = "near-term earnings and guidance"
        elif time_horizon == "long_term":
            focus_period = "5-year"
            metrics_focus = "strategic positioning and TAM"
        else:
            focus_period = "annual"
            metrics_focus = "sustainable competitive advantages"
        
        output_data = {
            "phase_1_prompts": {
                "financial": (
                    f"Gather comprehensive {focus_period} financial data for {ticker}. "
                    f"Focus on: revenue trends, margin analysis, cash flow, "
                    f"balance sheet strength, and {metrics_focus} relevant to: {thesis_statement}. "
                    f"Include 5-year historical data and peer comparisons. "
                    f"Output as structured JSON with sources."
                ),
                "news_sentiment": (
                    f"Analyze recent news and market sentiment for {ticker} (last 90 days). "
                    f"Focus on: market-moving events, analyst opinions, "
                    f"earnings surprises, management changes, and sentiment related to: {thesis_statement}. "
                    f"Include aggregate sentiment score and key themes. "
                    f"Output as structured JSON with article summaries."
                ),
                "competitors": (
                    f"Map the competitive landscape for {ticker}. "
                    f"Focus on: market share, competitive advantages (moat), "
                    f"peer comparison, and competitive dynamics relevant to: {thesis_statement}. "
                    f"Identify 4-6 key competitors with financial comparisons. "
                    f"Output as structured JSON with peer metrics."
                ),
                "market_trends": (
                    f"Analyze market and sector trends affecting {ticker}. "
                    f"Focus on: industry growth, macro factors, "
                    f"regulatory environment, and technology disruption related to: {thesis_statement}. "
                    f"Include ESG considerations and ESG scores. "
                    f"Output as structured JSON with trend analysis."
                ),
            },
            "metadata": {
                "decomposition_confidence": 0.85,
                "estimated_complexity": "medium",
                "special_considerations": [],
            },
        }
        
        return AgentOutput(
            phase=self.phase,
            data=output_data,
            confidence=0.85,
            provenance=[{"source": "fallback_template"}],
            metadata={"model": "fallback"},
        )
    
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate question generator output.
        
        Args:
            output: Agent output to validate
            
        Returns:
            True if valid
        """
        data = output.data
        
        # Check required keys
        if "phase_1_prompts" not in data:
            logger.error("Missing phase_1_prompts in output")
            return False
        
        prompts = data["phase_1_prompts"]
        required_prompts = ["financial", "news_sentiment", "competitors", "market_trends"]
        
        for key in required_prompts:
            if key not in prompts:
                logger.error(f"Missing prompt: {key}")
                return False
            if not isinstance(prompts[key], str) or len(prompts[key]) < 10:
                logger.error(f"Invalid prompt for {key}: too short or not string")
                return False
        
        # Check metadata
        if "metadata" not in data:
            logger.error("Missing metadata in output")
            return False
        
        metadata = data["metadata"]
        if "decomposition_confidence" not in metadata:
            logger.error("Missing decomposition_confidence in metadata")
            return False
        
        return True
