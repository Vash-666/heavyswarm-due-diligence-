"""Tests for prompt loader."""

import pytest

from heavyswarm.services.prompt_loader import PromptLoader


@pytest.fixture
def prompt_loader():
    """Create prompt loader fixture."""
    return PromptLoader(version="v1.0.0")


def test_load_prompt_exists(prompt_loader):
    """Test loading an existing prompt."""
    prompt = prompt_loader.load_prompt("question_generator", "system.txt")
    
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    assert "Question Generator" in prompt


def test_load_prompt_not_exists(prompt_loader):
    """Test loading a non-existent prompt."""
    with pytest.raises(FileNotFoundError):
        prompt_loader.load_prompt("nonexistent", "prompt.txt")


def test_render_prompt(prompt_loader):
    """Test rendering a prompt with variables."""
    variables = {
        "ticker": "AAPL",
        "thesis": "Test thesis",
        "time_horizon": "medium_term",
        "risk_tolerance": "moderate",
        "position_size": "5",
        "priority": "high",
    }
    
    prompt = prompt_loader.render_prompt(
        "question_generator",
        "decompose.txt",
        variables,
    )
    
    assert "AAPL" in prompt
    assert "Test thesis" in prompt


def test_get_agent_config(prompt_loader):
    """Test getting agent configuration."""
    config = prompt_loader.get_agent_config("question_generator")
    
    assert "model" in config
    assert "temperature" in config
    assert "max_tokens" in config


def test_get_all_prompts_for_agent(prompt_loader):
    """Test getting all prompts for an agent."""
    prompts = prompt_loader.get_all_prompts_for_agent("question_generator")
    
    assert isinstance(prompts, dict)
    assert len(prompts) > 0
    assert "system" in prompts


def test_list_available_agents(prompt_loader):
    """Test listing available agents."""
    agents = prompt_loader.list_available_agents()
    
    assert isinstance(agents, list)
    assert "question_generator" in agents
    assert "researcher" in agents
    assert "financial_analyst" in agents


def test_get_quality_equation(prompt_loader):
    """Test getting quality equation."""
    equation = prompt_loader.get_quality_equation()
    
    assert "prompts" in equation
    assert "memory" in equation
    assert "model" in equation
    assert "tools" in equation
    assert sum(equation.values()) == 1.0