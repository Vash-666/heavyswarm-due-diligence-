"""Prompt loading utility for HeavySwarm agents."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class PromptLoader:
    """Loads and manages prompt templates for agents."""
    
    def __init__(self, prompts_dir: Optional[Path] = None):
        """Initialize prompt loader.
        
        Args:
            prompts_dir: Base directory for prompts. Defaults to project prompts dir.
        """
        if prompts_dir is None:
            # Find prompts directory relative to this file
            # src/heavyswarm/utils/ -> prompts/
            self.prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts" / "v1.0.0"
        else:
            self.prompts_dir = prompts_dir
        
        self._cache: Dict[str, str] = {}
        self._registry: Optional[Dict[str, Any]] = None
        
        logger.debug(f"PromptLoader initialized with dir: {self.prompts_dir}")
    
    def _load_registry(self) -> Dict[str, Any]:
        """Load the prompt registry.
        
        Returns:
            Registry dictionary
        """
        if self._registry is None:
            registry_path = self.prompts_dir / "registry.json"
            if registry_path.exists():
                with open(registry_path, "r") as f:
                    self._registry = json.load(f)
            else:
                self._registry = {}
                logger.warning(f"Registry not found at {registry_path}")
        return self._registry
    
    def load_prompt(self, agent_name: str, prompt_file: str) -> str:
        """Load a specific prompt file.
        
        Args:
            agent_name: Name of the agent (e.g., 'question_generator')
            prompt_file: Name of the prompt file (e.g., 'system.txt')
            
        Returns:
            Prompt content
            
        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        cache_key = f"{agent_name}/{prompt_file}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        prompt_path = self.prompts_dir / agent_name / prompt_file
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")
        
        with open(prompt_path, "r") as f:
            content = f.read()
        
        self._cache[cache_key] = content
        logger.debug(f"Loaded prompt: {cache_key}")
        
        return content
    
    def load_agent_prompts(self, agent_name: str) -> Dict[str, str]:
        """Load all prompts for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Dictionary mapping prompt names to content
        """
        agent_dir = self.prompts_dir / agent_name
        
        if not agent_dir.exists():
            raise FileNotFoundError(f"Agent prompts not found: {agent_dir}")
        
        prompts = {}
        for prompt_file in agent_dir.glob("*.txt"):
            prompt_name = prompt_file.stem
            prompts[prompt_name] = self.load_prompt(agent_name, prompt_file.name)
        
        return prompts
    
    def get_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Get agent configuration from registry.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Agent configuration dictionary
        """
        registry = self._load_registry()
        agents = registry.get("agents", {})
        
        if agent_name not in agents:
            raise ValueError(f"Agent not found in registry: {agent_name}")
        
        return agents[agent_name]
    
    def render_prompt(
        self,
        template: str,
        variables: Dict[str, Any],
    ) -> str:
        """Render a prompt template with variables.
        
        Args:
            template: Prompt template with {{variable}} placeholders
            variables: Dictionary of variables to substitute
            
        Returns:
            Rendered prompt
        """
        result = template
        
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            
            # Convert value to string
            if isinstance(value, (dict, list)):
                str_value = json.dumps(value, indent=2)
            else:
                str_value = str(value) if value is not None else ""
            
            result = result.replace(placeholder, str_value)
        
        return result
    
    def load_and_render(
        self,
        agent_name: str,
        prompt_file: str,
        variables: Dict[str, Any],
    ) -> str:
        """Load and render a prompt in one call.
        
        Args:
            agent_name: Name of the agent
            prompt_file: Name of the prompt file
            variables: Variables to substitute
            
        Returns:
            Rendered prompt
        """
        template = self.load_prompt(agent_name, prompt_file)
        return self.render_prompt(template, variables)
    
    def clear_cache(self) -> None:
        """Clear the prompt cache."""
        self._cache.clear()
        logger.debug("Prompt cache cleared")
    
    def list_available_agents(self) -> List[str]:
        """List all agents with prompt directories.
        
        Returns:
            List of agent names
        """
        if not self.prompts_dir.exists():
            return []
        
        agents = []
        for item in self.prompts_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                agents.append(item.name)
        
        return sorted(agents)
    
    def list_agent_prompts(self, agent_name: str) -> List[str]:
        """List all prompt files for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            List of prompt file names
        """
        agent_dir = self.prompts_dir / agent_name
        
        if not agent_dir.exists():
            return []
        
        prompts = []
        for prompt_file in agent_dir.glob("*.txt"):
            prompts.append(prompt_file.name)
        
        return sorted(prompts)


# Global prompt loader instance
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Get the global prompt loader instance.
    
    Returns:
        PromptLoader instance
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
