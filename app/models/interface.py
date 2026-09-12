from typing import Protocol, List
from dataclasses import dataclass

@dataclass
class ModelInfo:
    """Information about an AI model."""
    id: str
    name: str
    description: str
    is_downloaded: bool = False
    
class ModelManager(Protocol):
    """Protocol defining the interface for model management."""
    
    def list_available_models(self) -> List[ModelInfo]:
        """List all available models."""
        ...
        
    def download_model(self, model_id: str, progress_callback=None) -> bool:
        """Download a specific model."""
        ...
