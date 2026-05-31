# Grok API Integration Guide

This document describes the xAI Grok integration in HeavySwarm Due Diligence Engine.

## Overview

HeavySwarm now supports xAI's Grok models as a first-class LLM provider alongside OpenAI and Anthropic. Grok models are particularly well-suited for reasoning-intensive tasks like scenario analysis and verification.

## Supported Models

| Model | Best For | Input Price | Output Price |
|-------|----------|-------------|--------------|
| `grok-4.20-reasoning` | Complex reasoning, analysis | $0.015/1K | $0.075/1K |
| `grok-4.3` | Balanced performance | $0.005/1K | $0.015/1K |
| `grok-2` | Fast, cost-effective tasks | $0.002/1K | $0.010/1K |

## Configuration

### 1. Set up API Key

Add your xAI API key to `.env`:

```bash
XAI_API_KEY=xai-your-api-key-here
```

### 2. Agent Model Assignment

Grok models are pre-configured for reasoning-intensive agents:

```yaml
# config/agents.yaml
strategist:
  model: grok-4.20-reasoning  # Complex scenario analysis
  fallback_chain:
    - grok-4.20-reasoning
    - claude-3-5-sonnet-20241022
    - gpt-4o

verifier:
  model: grok-4.20-reasoning  # Fact-checking & bias detection
  fallback_chain:
    - grok-4.20-reasoning
    - claude-3-5-sonnet-20241022
    - gpt-4o
```

### 3. Custom Model Selection

To use Grok for other agents, modify `config/agents.yaml`:

```yaml
financial_analyst:
  model: grok-4.3  # Use Grok for financial analysis
  temperature: 0.1
  max_tokens: 6000
```

## Usage Examples

### Direct LLM Client Usage

```python
from heavyswarm.services.llm_client import LLMClient, LLMRequest
from heavyswarm.core.config import settings

# Initialize client
llm_client = LLMClient(settings)

# Create request for Grok
request = LLMRequest(
    model="grok-4.20-reasoning",
    messages=[
        {"role": "system", "content": "You are an expert investment analyst."},
        {"role": "user", "content": "Analyze the bull case for AAPL..."}
    ],
    temperature=0.3,
    max_tokens=4000,
)

# Get completion
response = await llm_client.complete(request)
print(f"Response: {response.content}")
print(f"Cost: ${response.cost_usd:.4f}")
print(f"Tokens: {response.usage['total_tokens']}")
```

### Using Grok for Specific Tasks

```python
# Scenario analysis with Grok reasoning
request = LLMRequest(
    model="grok-4.20-reasoning",
    messages=[
        {"role": "system", "content": "Create bull/base/bear scenarios."},
        {"role": "user", "content": "Company: Tesla (TSLA), Current Price: $250"}
    ],
    temperature=0.3,
    max_tokens=6000,
)

# Fact-checking with Grok
verify_request = LLMRequest(
    model="grok-4.20-reasoning",
    messages=[
        {"role": "system", "content": "Verify claims and detect biases."},
        {"role": "user", "content": "Claim: AAPL revenue grew 15% YoY"}
    ],
    temperature=0.1,
    max_tokens=4000,
)
```

### Fallback Behavior

If Grok is unavailable, the system automatically falls back:

```
grok-4.20-reasoning → claude-3-5-sonnet-20241022 → gpt-4o
```

This ensures your diligence workflows remain operational even if one provider experiences issues.

## Cost Tracking

The LLM client automatically tracks costs for all Grok calls:

```python
# Get cost metrics
metrics = llm_client.get_cost_metrics()
grok_metrics = metrics.get("grok-4.20-reasoning")

print(f"Total calls: {grok_metrics.total_calls}")
print(f"Total cost: ${grok_metrics.total_cost_usd:.2f}")
print(f"Avg cost/call: ${grok_metrics.average_cost_per_call:.4f}")
```

## Rate Limiting

Grok models have built-in rate limiting:

| Model | Requests/min | Tokens/min |
|-------|--------------|------------|
| grok-4.20-reasoning | 1,000 | 2,000,000 |
| grok-4.3 | 2,000 | 4,000,000 |
| grok-2 | 3,000 | 6,000,000 |

The client automatically handles rate limiting with token bucket algorithm.

## Circuit Breaker

Each provider (including Grok) has its own circuit breaker:

```python
# Check circuit states
states = llm_client.get_circuit_states()
print(f"Grok circuit: {states['grok'].name}")  # CLOSED, OPEN, or HALF_OPEN
```

The circuit breaker opens after 5 consecutive failures and recovers after 30 seconds.

## Testing

Run Grok integration tests:

```bash
pytest tests/unit/test_grok_integration.py -v
```

## Troubleshooting

### "xAI API key not configured"
- Ensure `XAI_API_KEY` is set in your `.env` file
- Verify the key is valid at https://console.x.ai

### Rate limit errors
- The client automatically retries with exponential backoff
- Consider using `grok-2` for higher throughput

### Fallback not working
- Ensure fallback models (Claude, GPT-4o) are configured with API keys
- Check the fallback chain in `config/agents.yaml`

## Migration from Other Providers

To migrate an existing agent from Claude/OpenAI to Grok:

1. Update `config/agents.yaml`:
```yaml
agent_name:
  model: grok-4.20-reasoning  # or grok-4.3, grok-2
```

2. No code changes required - the LLM client handles provider switching automatically

3. Monitor cost differences using the cost tracking metrics

## Best Practices

1. **Use `grok-4.20-reasoning`** for complex reasoning tasks (strategist, verifier)
2. **Use `grok-4.3`** for balanced performance on general tasks
3. **Use `grok-2`** for high-volume, cost-sensitive operations
4. **Always configure fallback chains** to ensure system resilience
5. **Monitor costs** - reasoning models are more expensive but provide better results

## API Reference

The Grok API is OpenAI-compatible. See [xAI Documentation](https://docs.x.ai) for full API details.

### Key Differences from OpenAI

- Base URL: `https://api.x.ai/v1`
- Authentication: Same Bearer token format
- Response format: Identical to OpenAI chat completions

## Support

For Grok-specific issues:
- xAI Status: https://status.x.ai
- HeavySwarm Issues: GitHub Issues
