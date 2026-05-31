"""Prompt loader for managing prompt templates."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class PromptLoader:
    """Loads and manages prompt templates from the prompts directory."""
    
    def __init__(self, version: str = "v1.0.0"):
        """Initialize the prompt loader.
        
        Args:
            version: Prompt version to use
        """
        self.version = version
        self.base_path = Path(__file__).parent.parent.parent.parent / "prompts" / version
        self._registry: Optional[Dict] = None
        self._cache: Dict[str, str] = {}
    
    def _load_registry(self) -> Dict:
        """Load the prompt registry.
        
        Returns:
            Registry dictionary
        """
        if self._registry is None:
            registry_path = self.base_path / "registry.json"
            with open(registry_path, "r") as f:
                self._registry = json.load(f)
        return self._registry
    
    def load_prompt(self, agent: str, prompt_file: str) -> str:
        """Load a prompt template.
        
        Args:
            agent: Agent name (e.g., "question_generator")
            prompt_file: Prompt file name (e.g., "system.txt")
            
        Returns:
            Prompt template string
        """
        cache_key = f"{agent}/{prompt_file}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        prompt_path = self.base_path / agent / prompt_file
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")
        
        with open(prompt_path, "r") as f:
            content = f.read()
        
        self._cache[cache_key] = content
        return content
    
    def render_prompt(
        self,
        agent: str,
        prompt_file: str,
        variables: Dict[str, Any],
    ) -> str:
        """Load and render a prompt template with variables.
        
        Args:
            agent: Agent name
            prompt_file: Prompt file name
            variables: Variables to substitute
            
        Returns:
            Rendered prompt
        """
        template = self.load_prompt(agent, prompt_file)
        
        # Simple variable substitution
        # Supports {{variable}} syntax
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            
            # Convert value to string
            if isinstance(value, (dict, list)):
                str_value = json.dumps(value, indent=2, default=str)
            else:
                str_value = str(value)
            
            template = template.replace(placeholder, str_value)
        
        # Check for unreplaced variables
        unreplaced = re.findall(r'\{\{(\w+)\}\}', template)
        if unreplaced:
            logger.warning(f"Unreplaced variables in prompt: {unreplaced}")
        
        return template
    
    def get_agent_config(self, agent: str) -> Dict[str, Any]:
        """Get configuration for an agent from registry.
        
        Args:
            agent: Agent name
            
        Returns:
            Agent configuration
        """
        registry = self._load_registry()
        return registry.get("agents", {}).get(agent, {})
    
    def get_all_prompts_for_agent(self, agent: str) -> Dict[str, str]:
        """Get all prompt templates for an agent.
        
        Args:
            agent: Agent name
            
        Returns:
            Dictionary of prompt name to content
        """
        agent_path = self.base_path / agent
        
        if not agent_path.exists():
            return {}
        
        prompts = {}
        for prompt_file in agent_path.glob("*.txt"):
            prompts[prompt_file.stem] = self.load_prompt(agent, prompt_file.name)
        
        return prompts
    
    def list_available_agents(self) -> List[str]:
        """List all available agents.
        
        Returns:
            List of agent names
        """
        registry = self._load_registry()
        return list(registry.get("agents", {}).keys())
    
    def get_quality_equation(self) -> Dict[str, float]:
        """Get the quality equation weights.
        
        Returns:
            Quality equation dictionary
        """
        registry = self._load_registry()
        return registry.get("quality_equation", {
            "prompts": 0.65,
            "memory": 0.20,
            "model": 0.10,
            "tools": 0.05,
        })