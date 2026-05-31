"""Tests for xAI Grok LLM integration.

These tests verify the Grok integration without requiring all dependencies.
"""

import os
import sys
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))


class TestGrokPricingConfig:
    """Test Grok pricing configuration exists in llm_client.py."""

    def test_grok_models_in_llm_client(self):
        """Verify Grok models are defined in llm_client.py source."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        # Check for Grok model pricing entries
        assert '"grok-4.20-reasoning"' in content, "grok-4.20-reasoning should be in MODEL_PRICING"
        assert '"grok-4.3"' in content, "grok-4.3 should be in MODEL_PRICING"
        assert '"grok-2"' in content, "grok-2 should be in MODEL_PRICING"
        
        # Check for xAI pricing values
        assert '0.015' in content and '0.075' in content, "Grok reasoning pricing should be defined"

    def test_grok_rate_limits_in_llm_client(self):
        """Verify Grok rate limits are defined."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        # Check for Grok rate limit entries
        assert '"grok-4.20-reasoning"' in content, "grok-4.20-reasoning should have rate limits"
        assert '"grok-4.3"' in content, "grok-4.3 should have rate limits"
        assert '"grok-2"' in content, "grok-2 should have rate limits"

    def test_grok_client_property_exists(self):
        """Verify grok_client property is defined."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        # Check for grok_client property
        assert 'def grok_client' in content, "grok_client property should exist"
        assert 'api.x.ai' in content, "xAI base URL should be configured"
        assert '_grok_client' in content, "_grok_client private attribute should exist"

    def test_grok_model_detection(self):
        """Verify _is_grok_model method exists."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        assert 'def _is_grok_model' in content, "_is_grok_model method should exist"
        assert 'model.startswith("grok-")' in content, "Should check for grok- prefix"

    def test_grok_token_counting(self):
        """Verify Grok token counting is implemented."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        assert 'def count_tokens_grok' in content, "count_tokens_grok method should exist"

    def test_grok_api_call_methods(self):
        """Verify Grok API call methods exist."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        assert 'def _call_grok' in content, "_call_grok method should exist"
        assert 'def _stream_grok' in content, "_stream_grok method should exist"

    def test_grok_fallback_chain(self):
        """Verify Grok fallback chain is defined."""
        llm_client_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'services', 'llm_client.py'
        )
        
        with open(llm_client_path, 'r') as f:
            content = f.read()
        
        # Check fallback chain for Grok
        assert '"grok-4.20-reasoning":' in content, "Grok reasoning should have fallback"
        assert '"grok-4.3":' in content, "Grok 4.3 should have fallback"
        assert '"grok-2":' in content, "Grok 2 should have fallback"


class TestGrokConfig:
    """Test Grok configuration in agents.yaml."""

    def test_agents_yaml_exists(self):
        """Test agents.yaml configuration file exists."""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        assert os.path.exists(config_path), "agents.yaml should exist"

    def test_grok_in_agents_yaml(self):
        """Test Grok is configured in agents.yaml."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Check that Grok models are in pricing section
        pricing = config.get('pricing', {})
        assert 'grok-4.20-reasoning' in pricing, "grok-4.20-reasoning should be in pricing"
        assert 'grok-4.3' in pricing, "grok-4.3 should be in pricing"
        assert 'grok-2' in pricing, "grok-2 should be in pricing"
        
        # Check pricing values
        grok_reasoning = pricing['grok-4.20-reasoning']
        assert grok_reasoning['input'] == 0.015
        assert grok_reasoning['output'] == 0.075
        
        # Check that strategist uses Grok
        agents = config.get('agents', {})
        strategist = agents.get('strategist', {})
        assert 'grok' in strategist.get('model', ''), "Strategist should use Grok"
        
        # Check that verifier uses Grok
        verifier = agents.get('verifier', {})
        assert 'grok' in verifier.get('model', ''), "Verifier should use Grok"
        
        # Check fallback chains
        assert 'fallback_chain' in strategist, "Strategist should have fallback chain"
        assert 'fallback_chain' in verifier, "Verifier should have fallback chain"

    def test_grok_rate_limits_in_agents_yaml(self):
        """Test Grok rate limits in agents.yaml."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        rate_limits = config.get('rate_limits', {})
        assert 'grok-4.20-reasoning' in rate_limits, "Grok reasoning should have rate limits"
        assert 'grok-4.3' in rate_limits, "Grok 4.3 should have rate limits"
        assert 'grok-2' in rate_limits, "Grok 2 should have rate limits"


class TestGrokEnvConfig:
    """Test Grok environment configuration."""

    def test_xai_api_key_in_env_example(self):
        """Test XAI_API_KEY placeholder exists."""
        env_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '.env.example'
        )
        
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Check for XAI_API_KEY
        assert 'XAI_API_KEY=' in content, "XAI_API_KEY should be in .env.example"
        
        # Check for Grok-specific settings
        assert 'GROK' in content or 'grok' in content.lower(), "Grok should be mentioned"

    def test_grok_config_settings_in_env(self):
        """Test Grok-specific config in .env.example."""
        env_path = os.path.join(
            os.path.dirname(__file__), '..', '..', '.env.example'
        )
        
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Check for Grok model documentation
        assert 'grok-4.20-reasoning' in content.lower() or 'grok-4' in content.lower(), \
            "Grok models should be documented in .env.example"


class TestGrokCoreConfig:
    """Test Grok in core config.py."""

    def test_xai_api_key_in_config(self):
        """Test xai_api_key field exists in Settings."""
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'src', 'heavyswarm', 'core', 'config.py'
        )
        
        with open(config_path, 'r') as f:
            content = f.read()
        
        assert 'xai_api_key' in content, "xai_api_key should be in Settings"
        assert 'XAI_API_KEY' in content, "XAI_API_KEY alias should be defined"


class TestGrokDocumentation:
    """Test Grok documentation exists."""

    def test_grok_integration_doc_exists(self):
        """Test Grok integration documentation exists."""
        doc_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'docs', 'GROK_INTEGRATION.md'
        )
        assert os.path.exists(doc_path), "GROK_INTEGRATION.md should exist"

    def test_grok_in_readme(self):
        """Test Grok is mentioned in README."""
        readme_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'README.md'
        )
        
        with open(readme_path, 'r') as f:
            content = f.read()
        
        assert 'Grok' in content or 'grok' in content.lower(), "Grok should be in README"
        assert 'xAI' in content, "xAI should be mentioned in README"

    def test_grok_in_architecture(self):
        """Test Grok is mentioned in ARCHITECTURE.md."""
        arch_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'docs', 'ARCHITECTURE.md'
        )
        
        with open(arch_path, 'r') as f:
            content = f.read()
        
        assert 'Grok' in content or 'grok' in content.lower(), "Grok should be in ARCHITECTURE"


class TestGrokPricingValues:
    """Test Grok pricing values are reasonable."""

    def test_grok_reasoning_pricing(self):
        """Test grok-4.20-reasoning pricing."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        pricing = config['pricing']['grok-4.20-reasoning']
        assert pricing['input'] == 0.015, "Input price should be $0.015/1K tokens"
        assert pricing['output'] == 0.075, "Output price should be $0.075/1K tokens"
        assert pricing['output'] > pricing['input'], "Output should be more expensive"

    def test_grok_4_3_pricing(self):
        """Test grok-4.3 pricing."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        pricing = config['pricing']['grok-4.3']
        assert pricing['input'] == 0.005, "Input price should be $0.005/1K tokens"
        assert pricing['output'] == 0.015, "Output price should be $0.015/1K tokens"

    def test_grok_2_pricing(self):
        """Test grok-2 pricing."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        pricing = config['pricing']['grok-2']
        assert pricing['input'] == 0.002, "Input price should be $0.002/1K tokens"
        assert pricing['output'] == 0.010, "Output price should be $0.010/1K tokens"

    def test_grok_pricing_progression(self):
        """Test Grok pricing follows expected progression."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        pricing = config['pricing']
        
        # Reasoning should be most expensive
        assert pricing['grok-4.20-reasoning']['input'] > pricing['grok-4.3']['input']
        assert pricing['grok-4.20-reasoning']['output'] > pricing['grok-4.3']['output']
        
        # 4.3 should be more expensive than 2
        assert pricing['grok-4.3']['input'] > pricing['grok-2']['input']
        assert pricing['grok-4.3']['output'] > pricing['grok-2']['output']


class TestGrokAgentAssignments:
    """Test Grok is assigned to appropriate agents."""

    def test_strategist_uses_grok_reasoning(self):
        """Test strategist uses Grok reasoning model."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        strategist = config['agents']['strategist']
        assert strategist['model'] == 'grok-4.20-reasoning', \
            "Strategist should use grok-4.20-reasoning"
        assert strategist['temperature'] == 0.3
        assert strategist['max_tokens'] == 6000

    def test_verifier_uses_grok_reasoning(self):
        """Test verifier uses Grok reasoning model."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        verifier = config['agents']['verifier']
        assert verifier['model'] == 'grok-4.20-reasoning', \
            "Verifier should use grok-4.20-reasoning"
        assert verifier['temperature'] == 0.1
        assert verifier['max_tokens'] == 8000

    def test_fallback_chains_include_claude_and_gpt(self):
        """Test fallback chains include Claude and GPT."""
        import yaml
        
        config_path = os.path.join(
            os.path.dirname(__file__), '..', '..', 'config', 'agents.yaml'
        )
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        strategist = config['agents']['strategist']
        verifier = config['agents']['verifier']
        
        # Both should have fallback chains
        assert 'fallback_chain' in strategist
        assert 'fallback_chain' in verifier
        
        # Fallback should include Claude and GPT
        for agent in [strategist, verifier]:
            fallback = agent['fallback_chain']
            assert 'grok-4.20-reasoning' in fallback
            assert 'claude-3-5-sonnet-20241022' in fallback
            assert 'gpt-4o' in fallback
