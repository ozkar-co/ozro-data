"""Entity extractors (Etapa 2+)."""

from .maps import extract_maps
from .mobs import extract_mobs
from .items import extract_items

__all__ = ["extract_maps", "extract_mobs", "extract_items"]
