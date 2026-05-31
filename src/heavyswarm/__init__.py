"""HeavySwarm Investment Due Diligence Engine.

A 7-agent multi-phase analysis system for institutional-quality investment research.
"""

__version__ = "1.0.0"
__author__ = "HeavySwarm Team"
__email__ = "team@heavyswarm.io"

from heavyswarm.core.config import Settings
from heavyswarm.core.state import DiligenceState

__all__ = ["Settings", "DiligenceState", "__version__"]
