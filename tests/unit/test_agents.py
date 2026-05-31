"""Tests for agent implementations."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from heavyswarm.agents import (
    FinancialAnalystAgent,
    QualityGuardianAgent,
    QuestionGeneratorAgent,
    ResearcherAgent,
    RiskAnalystAgent,
    StrategistAgent,
    VerifierAgent,
    WriterAgent,
)
from heavyswarm.core.agent_base import AgentConfig, AgentInput, AgentOutput
from heavyswarm.core.enums import AgentPhase
from heavyswarm.core.state import InvestmentThesis


@pytest.fixture
def agent_config():
    """Create agent configuration fixture."""
    return AgentConfig(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=4000,
        timeout_seconds=60,
        retry_attempts=3,
    )


@pytest.fixture
def sample_thesis():
    """Create sample investment thesis fixture."""
    return InvestmentThesis(
        ticker="AAPL",
        thesis="AI integration will drive services growth",
        time_horizon="medium_term",
        risk_tolerance="moderate",
        position_size=0.05,
        priority="high",
    )


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.fixture
def mock_data_sources():
    """Create mock data sources."""
    alpha_vantage = MagicMock()
    alpha_vantage.get_company_overview = AsyncMock()
    alpha_vantage.get_income_statement = AsyncMock()
    alpha_vantage.get_balance_sheet = AsyncMock()
    alpha_vantage.get_cash_flow = AsyncMock()
    alpha_vantage.get_quote = AsyncMock()
    
    news_api = MagicMock()
    news_api.get_company_news = AsyncMock()
    news_api.analyze_sentiment = AsyncMock()
    
    sec_edgar = MagicMock()
    sec_edgar.get_recent_filings = AsyncMock()
    
    return {
        "alpha_vantage": alpha_vantage,
        "news_api": news_api,
        "sec_edgar": sec_edgar,
    }


@pytest.fixture
def mock_verification_service():
    """Create mock verification service."""
    service = MagicMock()
    service.verify_data_point = AsyncMock()
    return service


class TestQuestionGeneratorAgent:
    """Test cases for QuestionGeneratorAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return QuestionGeneratorAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute_with_llm(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution with LLM."""
        # Mock LLM response
        mock_llm_client.complete.return_value = MagicMock(
            content='{"phase_1_prompts": {"financial": "Test financial", "news_sentiment": "Test news", "competitors": "Test competitors", "market_trends": "Test trends"}, "metadata": {"decomposition_confidence": 0.92}}',
            model="gpt-4o",
            response_time_ms=1000,
            usage={"total_tokens": 500},
        )
        
        input_data = AgentInput(thesis=sample_thesis)
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.QUESTION_GENERATOR
        assert "phase_1_prompts" in output.data
        assert output.confidence == 0.92
        mock_llm_client.complete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_fallback(self, agent, sample_thesis, mock_llm_client):
        """Test agent fallback execution."""
        # Mock LLM failure
        mock_llm_client.complete.side_effect = Exception("API Error")
        
        input_data = AgentInput(thesis=sample_thesis)
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.QUESTION_GENERATOR
        assert "phase_1_prompts" in output.data
        assert output.confidence == 0.85
    
    def test_validate_output_valid(self, agent):
        """Test output validation with valid data."""
        output = AgentOutput(
            phase=AgentPhase.QUESTION_GENERATOR,
            data={
                "phase_1_prompts": {
                    "financial": "Test financial prompt that is long enough",
                    "news_sentiment": "Test news prompt that is long enough",
                    "competitors": "Test competitors prompt that is long enough",
                    "market_trends": "Test market prompt that is long enough",
                },
                "metadata": {
                    "decomposition_confidence": 0.9,
                },
            },
            confidence=0.9,
        )
        
        assert agent.validate_output(output) is True
    
    def test_validate_output_invalid_missing_prompt(self, agent):
        """Test output validation with missing prompt."""
        output = AgentOutput(
            phase=AgentPhase.QUESTION_GENERATOR,
            data={
                "phase_1_prompts": {
                    "financial": "Test financial",
                    # Missing other prompts
                },
                "metadata": {"decomposition_confidence": 0.9},
            },
            confidence=0.9,
        )
        
        assert agent.validate_output(output) is False


class TestResearcherAgent:
    """Test cases for ResearcherAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client, mock_data_sources):
        """Create agent fixture."""
        return ResearcherAgent(
            agent_config,
            mock_llm_client,
            mock_data_sources["alpha_vantage"],
            mock_data_sources["news_api"],
            mock_data_sources["sec_edgar"],
        )
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_data_sources):
        """Test agent execution."""
        # Mock data source responses
        mock_data_sources["alpha_vantage"].get_company_overview.return_value = MagicMock(
            data={"RevenueTTM": "100000000", "Name": "Apple Inc"},
            error=None,
            retrieved_at=datetime.utcnow(),
        )
        mock_data_sources["alpha_vantage"].get_income_statement.return_value = MagicMock(
            data={"annualReports": []},
            error=None,
            retrieved_at=datetime.utcnow(),
        )
        mock_data_sources["sec_edgar"].get_recent_filings.return_value = MagicMock(
            data={"cik": "0000320193", "filings": []},
            error=None,
            retrieved_at=datetime.utcnow(),
        )
        mock_data_sources["news_api"].get_company_news.return_value = MagicMock(
            data={"articles": [{"title": "Test", "source": "Reuters"}]},
            error=None,
            retrieved_at=datetime.utcnow(),
        )
        mock_data_sources["news_api"].analyze_sentiment.return_value = MagicMock(
            data={"aggregate_sentiment": 0.5},
            error=None,
            retrieved_at=datetime.utcnow(),
        )
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "QUESTION_GENERATOR": {
                        "phase_1_prompts": {
                            "financial": "Test prompt",
                            "news_sentiment": "Test prompt",
                            "competitors": "Test prompt",
                            "market_trends": "Test prompt",
                        },
                    },
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.RESEARCHER
        assert "financial_data" in output.data
        assert "news_sentiment" in output.data
        assert output.confidence > 0
    
    def test_validate_output(self, agent):
        """Test output validation."""
        output = AgentOutput(
            phase=AgentPhase.RESEARCHER,
            data={
                "financial_data": {},
                "news_sentiment": {},
                "competitive_landscape": {},
                "market_trends": {},
                "provenance": {"data_points": 10, "verified_count": 8},
            },
            confidence=0.88,
        )
        
        assert agent.validate_output(output) is True


class TestFinancialAnalystAgent:
    """Test cases for FinancialAnalystAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return FinancialAnalystAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        # Mock LLM responses
        mock_llm_client.complete.side_effect = [
            MagicMock(
                content='{"dcf": {"fair_value": 220, "wacc": 0.085, "confidence": 0.85}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
            MagicMock(
                content='{"comps": {"weighted_average": 210, "confidence": 0.80}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
            MagicMock(
                content='{"precedent": {"ev_ebitda_median": 215, "confidence": 0.75}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
        ]
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "RESEARCHER": {
                        "financial_data": {"metrics": {"revenue": {"value": 100}}},
                        "market_trends": {},
                    },
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.FINANCIAL_ANALYST
        assert "valuation_models" in output.data
        assert "price_target" in output.data
    
    def test_validate_output(self, agent):
        """Test output validation."""
        output = AgentOutput(
            phase=AgentPhase.FINANCIAL_ANALYST,
            data={
                "valuation_models": {
                    "dcf": {},
                    "comps": {},
                    "precedent": {},
                },
                "price_target": {"consensus": 215},
            },
            confidence=0.85,
        )
        
        assert agent.validate_output(output) is True


class TestRiskAnalystAgent:
    """Test cases for RiskAnalystAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return RiskAnalystAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        mock_llm_client.complete.side_effect = [
            MagicMock(
                content='{"risk_matrix": {"risk_matrix": {"market_risks": []}, "risk_score": {"overall": 45}, "confidence": 0.80}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
            MagicMock(
                content='{"stress_tests": {"recession_scenario": {}}, "confidence": 0.75}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
        ]
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "RESEARCHER": {"financial_data": {}},
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.RISK_ANALYST
        assert "risk_matrix" in output.data
        assert "risk_score" in output.data


class TestStrategistAgent:
    """Test cases for StrategistAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return StrategistAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        mock_llm_client.complete.side_effect = [
            MagicMock(
                content='{"scenarios": {"bull": {"probability": 0.25, "irr": 0.30}, "base": {"probability": 0.50, "irr": 0.15}, "bear": {"probability": 0.25, "irr": -0.10}}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
            MagicMock(
                content='{"devils_advocate": {"contrarian_thesis": "Test"}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
        ]
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "FINANCIAL_ANALYST": {"price_target": {"consensus": 220}},
                    "RISK_ANALYST": {"risk_matrix": {}},
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.STRATEGIST
        assert "scenarios" in output.data
        assert "devils_advocate" in output.data
        assert "expected_return" in output.data
    
    def test_validate_output_probabilities(self, agent):
        """Test validation of scenario probabilities."""
        output = AgentOutput(
            phase=AgentPhase.STRATEGIST,
            data={
                "scenarios": {
                    "bull": {"probability": 0.30},
                    "base": {"probability": 0.50},
                    "bear": {"probability": 0.20},
                },
                "devils_advocate": {},
                "expected_return": {},
            },
            confidence=0.80,
        )
        
        assert agent.validate_output(output) is True


class TestVerifierAgent:
    """Test cases for VerifierAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client, mock_verification_service):
        """Create agent fixture."""
        return VerifierAgent(agent_config, mock_llm_client, mock_verification_service)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        mock_llm_client.complete.side_effect = [
            MagicMock(
                content='{"fact_check": {"summary": {"total_claims": 40, "verified": 36, "verification_rate": 0.90}}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
            MagicMock(
                content='{"bias_detection": {"confirmation_bias": {"detected": false}, "anchoring_bias": {"detected": true, "severity": 2}}}',
                model="gpt-4o",
                response_time_ms=1000,
                usage={},
            ),
        ]
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "RESEARCHER": {"financial_data": {}},
                    "FINANCIAL_ANALYST": {},
                    "RISK_ANALYST": {},
                    "STRATEGIST": {},
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.VERIFIER
        assert "fact_check" in output.data
        assert "bias_detection" in output.data
        assert "confidence_score" in output.data


class TestWriterAgent:
    """Test cases for WriterAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return WriterAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        mock_llm_client.complete.return_value = MagicMock(
            content='{"memo": {"metadata": {"ticker": "AAPL"}, "executive_summary": {"recommendation": "buy"}, "investment_thesis": "", "valuation_analysis": "", "risk_assessment": "", "scenarios": ""}}',
            model="gpt-4o",
            response_time_ms=1000,
            usage={},
        )
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "VERIFIER": {"confidence_score": {"overall": 0.87}},
                    "FINANCIAL_ANALYST": {"price_target": {"consensus": 220}},
                    "RISK_ANALYST": {"risk_score": {"overall": 45}},
                    "STRATEGIST": {"scenarios": {"bull": {"irr": 0.30}, "base": {"irr": 0.15}, "bear": {"irr": -0.10}}},
                },
            },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.WRITER
        assert "memo" in output.data
        assert "trading_signal" in output.data
        assert output.data["trading_signal"]["action"] in ["buy", "sell", "hold"]


class TestQualityGuardianAgent:
    """Test cases for QualityGuardianAgent."""
    
    @pytest.fixture
    def agent(self, agent_config, mock_llm_client):
        """Create agent fixture."""
        return QualityGuardianAgent(agent_config, mock_llm_client)
    
    @pytest.mark.asyncio
    async def test_execute(self, agent, sample_thesis, mock_llm_client):
        """Test agent execution."""
        mock_llm_client.complete.return_value = MagicMock(
            content='{"quality_review": {"decision": "approve", "decision_reasoning": "Quality acceptable", "quality_score": 88, "concerns": [], "recommendations": []}}',
            model="gpt-4o",
            response_time_ms=1000,
            usage={},
        )
        
        input_data = AgentInput(
            thesis=sample_thesis,
            context={
                "previous_phases": {
                    "WRITER": {"memo": {}, "trading_signal": {}}},
                    "VERIFIER": {"confidence_score": {"overall": 0.87}},
                },
        )
        
        output = await agent.execute(input_data)
        
        assert output.phase == AgentPhase.QUALITY_GUARDIAN
        assert "review_decision" in output.data
        assert output.data["review_decision"] in ["approve", "reject", "escalate"]
    
    def test_should_trigger_low_confidence(self, agent, sample_thesis):
        """Test trigger with low confidence."""
        from heavyswarm.core.state import DiligenceState
        
        state = DiligenceState()
        state.thesis = sample_thesis
        state.overall_confidence = 0.80
        
        assert agent.should_trigger(state) is True
    
    def test_should_not_trigger_high_confidence(self, agent, sample_thesis):
        """Test no trigger with high confidence."""
        from heavyswarm.core.state import DiligenceState
        
        state = DiligenceState()
        state.thesis = sample_thesis
        state.thesis.position_size = 0.03
        state.overall_confidence = 0.90
        
        assert agent.should_trigger(state) is False