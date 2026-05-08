"""Language registry package."""

from .registry import REGISTRY, LanguageRegistry
from .spec import LanguageSpec

__all__ = ["LanguageSpec", "LanguageRegistry", "REGISTRY"]
