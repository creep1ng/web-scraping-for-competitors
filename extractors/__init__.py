from .beautifulsoup_extractor import (
    extract_products_from_html,
    get_pagination_info,
    parse_price,
    clean_text,
)
from .strategies import (
    ExtractionStrategy,
    DefaultStrategy,
    EmergenteStrategy,
    IngesolarStrategy,
    IneldecStrategy,
    get_strategy_for_url,
)

__all__ = [
    "extract_products_from_html",
    "get_pagination_info",
    "parse_price",
    "clean_text",
    "ExtractionStrategy",
    "DefaultStrategy",
    "EmergenteStrategy",
    "IngesolarStrategy",
    "IneldecStrategy",
    "get_strategy_for_url",
]
