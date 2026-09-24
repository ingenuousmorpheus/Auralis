"""R&B Theory Atlas: era-aware composition knowledge (AU-03B). Data only, no generation."""

from .atlas import candidates, eras, load_atlas, suggest_keys
from .schema import AtlasError, validate_atlas

__all__ = ["AtlasError", "candidates", "eras", "load_atlas", "suggest_keys", "validate_atlas"]
