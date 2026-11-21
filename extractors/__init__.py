"""Entity extractors (Etapa 2+)."""

from .maps import extract_maps
from .mobs import extract_mobs
from .items import extract_items
from .npcs import extract_npcs
from .connections import extract_connections
from .map_distances import extract_map_distances
from .skills import extract_skills
from .spawns import extract_spawns

__all__ = [
    "extract_maps",
    "extract_mobs",
    "extract_items",
    "extract_npcs",
    "extract_connections",
    "extract_map_distances",
    "extract_skills",
    "extract_spawns",
]
