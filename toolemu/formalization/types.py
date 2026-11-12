"""Type definitions for the formalization module."""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class FormalizationConfig:
    """Configuration for intent formalization."""
    
    llm_model: str = "gpt-4o-mini-2024-07-18"
    temperature: float = 0.0
    max_retries: int = 3

@dataclass
class RefinementConfig:
    """Configuration for goal refinement."""
    
    llm_model: str = "gpt-5-mini-2025-08-07"
    temperature: float = 0.0
    max_retries: int = 3

class FormalizationError(Exception):
    """Exception raised when intent formalization fails after all retry attempts."""
    
    def __init__(self, message: str, history: List[Dict[str, Any]] = None):
        """
        Initialize FormalizationError.
        
        Args:
            message: Error message
            history: List of attempt dictionaries with 'attempt', 'code', and 'error' keys
        """
        super().__init__(message)
        self.history = history or []
    
    def __str__(self):
        error_str = super().__str__()
        if self.history:
            error_str += "\n\nAttempt History:"
            for attempt_info in self.history:
                error_str += f"\n  Attempt {attempt_info['attempt']}:"
                error_str += f"\n    Code: {attempt_info['code'][:100]}..."
                error_str += f"\n    Error: {attempt_info['error']}"

        return error_str

class IntentValidationError(Exception):
    """Exception raised when intent validation fails."""
    

