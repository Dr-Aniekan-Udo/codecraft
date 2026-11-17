import importlib
from typing import TYPE_CHECKING

try:
    import safe_module
except ImportError:
    safe_module = None

if TYPE_CHECKING:
    from annotations_only import Typed

importlib.import_module("dynamic_module")


def load(name: str) -> object:
    return importlib.import_module(name)
