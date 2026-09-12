"""
Typed error hierarchy for the NOVA model management layer.
"""


class ModelError(Exception):
    """Base for all model-management errors."""


class ModelNotFoundError(ModelError):
    """Raised when a requested model_id is not in the registry."""

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        super().__init__(f"Model '{model_id}' is not registered.")


class ModelNotInstalledError(ModelError):
    """Raised when the model's files are missing from the models directory."""

    def __init__(self, model_id: str, models_dir: str) -> None:
        self.model_id = model_id
        self.models_dir = models_dir
        super().__init__(
            f"Model '{model_id}' is not installed in '{models_dir}'. "
            f"Download the weights first."
        )


class ModelValidationError(ModelError):
    """Raised when the installed model files fail integrity checks."""

    def __init__(self, model_id: str, messages: list[str]) -> None:
        self.model_id = model_id
        self.messages = messages
        super().__init__(f"Model '{model_id}' validation failed: {'; '.join(messages)}")


class ModelLoadError(ModelError):
    """Raised when loading model weights into memory fails."""

    def __init__(self, model_id: str, reason: str) -> None:
        self.model_id = model_id
        self.reason = reason
        super().__init__(f"Failed to load model '{model_id}': {reason}")


class RuntimeNotAvailableError(ModelError):
    """Raised when the required runtime (e.g. diffusers/torch) is not installed."""

    def __init__(self, runtime_name: str, install_hint: str = "") -> None:
        self.runtime_name = runtime_name
        msg = f"Runtime '{runtime_name}' is not available."
        if install_hint:
            msg += f" {install_hint}"
        super().__init__(msg)


class SpecValidationError(ModelError):
    """Raised when a ModelSpec itself fails validate()."""

    def __init__(self, model_id: str, messages: list[str]) -> None:
        self.model_id = model_id
        self.messages = messages
        super().__init__(f"Invalid spec for '{model_id}': {'; '.join(messages)}")
