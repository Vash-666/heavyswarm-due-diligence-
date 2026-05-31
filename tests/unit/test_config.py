"""Tests for configuration module."""

import os
from unittest.mock import patch

import pytest

from heavyswarm.core.config import Settings


class TestSettings:
    """Test cases for Settings class."""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_default_values(self):
        """Test default configuration values."""
        settings = Settings(_env_file=None)
        
        assert settings.api_host == "0.0.0.0"
        assert settings.api_port == 8000
        assert settings.log_level == "INFO"
        assert settings.environment == "development"
    
    @patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=True)
    def test_environment_detection_dev(self):
        """Test environment mode detection for development."""
        dev_settings = Settings(_env_file=None)
        assert dev_settings.is_development is True
        assert dev_settings.is_production is False
    
    @patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True)
    def test_environment_detection_prod(self):
        """Test environment mode detection for production."""
        prod_settings = Settings(_env_file=None)
        assert prod_settings.is_development is False
        assert prod_settings.is_production is True
    
    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True)
    def test_log_level_validation_debug(self):
        """Test log level validation for DEBUG."""
        settings = Settings(_env_file=None)
        assert settings.log_level == "DEBUG"
    
    @patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}, clear=True)
    def test_log_level_validation_error(self):
        """Test log level validation for ERROR."""
        settings = Settings(_env_file=None)
        assert settings.log_level == "ERROR"
    
    @patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True)
    def test_log_level_validation_invalid(self):
        """Test log level validation for invalid level."""
        with pytest.raises(ValueError):
            Settings(_env_file=None)
    
    def test_position_size_validation(self):
        """Test position size constraints."""
        from heavyswarm.core.state import InvestmentThesis
        from heavyswarm.core.enums import TimeHorizon, RiskTolerance
        
        # Valid position sizes
        for size in [0.01, 0.05, 0.10, 0.50, 1.0]:
            thesis = InvestmentThesis(
                ticker="AAPL",
                thesis="Test thesis with valid position size",
                position_size=size,
            )
            assert thesis.position_size == size
        
        # Invalid position sizes
        for size in [0, -0.1, 1.5]:
            with pytest.raises(ValueError):
                InvestmentThesis(
                    ticker="AAPL",
                    thesis="Test thesis with invalid position size",
                    position_size=size,
                )
    
    @patch.dict(os.environ, {"API_PORT": "9000", "LOG_LEVEL": "DEBUG"})
    def test_environment_variables(self):
        """Test loading from environment variables."""
        settings = Settings()
        
        assert settings.api_port == 9000
        assert settings.log_level == "DEBUG"
