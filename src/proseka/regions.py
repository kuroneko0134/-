"""Region definitions for the Project SEKAI master database mirrors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

__all__ = ["Region", "REGIONS", "get_region", "DEFAULT_REGION"]

_RAW_BASE = "https://raw.githubusercontent.com/Sekai-World"


@dataclass(frozen=True)
class Region:
    """A server region and the public mirror that carries its master data."""

    code: str
    label: str
    repository: str
    branch: str = "main"

    @property
    def base_url(self) -> str:
        return f"{_RAW_BASE}/{self.repository}/{self.branch}"

    def table_url(self, table: str) -> str:
        return f"{self.base_url}/{table}.json"


REGIONS: Dict[str, Region] = {
    "jp": Region("jp", "日本 (Project SEKAI)", "sekai-master-db-diff"),
    "en": Region("en", "Global (Colorful Stage!)", "sekai-master-db-en-diff"),
    "tc": Region("tc", "繁體中文", "sekai-master-db-tc-diff"),
    "kr": Region("kr", "한국어", "sekai-master-db-kr-diff"),
    "cn": Region("cn", "简体中文", "sekai-master-db-cn-diff"),
}

DEFAULT_REGION = "jp"


def get_region(code: str) -> Region:
    """Look up a region by code, case-insensitively."""
    try:
        return REGIONS[code.strip().lower()]
    except KeyError:
        known = ", ".join(sorted(REGIONS))
        raise ValueError(f"unknown region {code!r}; expected one of: {known}") from None
