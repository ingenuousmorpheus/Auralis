"""Song composer (AU-04+): brief → Song Blueprint. No audio yet."""

from .blueprint import BLUEPRINT_VERSION, build_blueprint, regenerate, revise
from .brief import parse_brief
from .validation import validate_blueprint

__all__ = ["BLUEPRINT_VERSION", "build_blueprint", "parse_brief", "regenerate", "revise", "validate_blueprint"]
