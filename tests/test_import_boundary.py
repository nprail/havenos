"""Hard rule from docs/specs/03: havenos.core must not import Qt."""
import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src" / "havenos" / "core"
FORBIDDEN = ("PySide6", "PyQt5", "PyQt6", "shiboken6", "havenos.bridge")


def test_core_has_no_qt_imports():
    offenders = []
    for py in CORE.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [("." * node.level) + (node.module or "")]
            for n in names:
                if n.startswith(FORBIDDEN) or n.startswith("..bridge"):
                    offenders.append(f"{py.relative_to(CORE)}: {n}")
    assert not offenders, offenders
