"""Common API response definitions."""

from typing import Dict, Any

NOT_FOUND_RESPONSE: Dict[int, Dict[str, Any]] = {404: {"description": "Not found"}}
