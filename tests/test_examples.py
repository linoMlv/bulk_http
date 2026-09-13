"""The bundled examples must stay importable and syntactically valid."""

import py_compile
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def test_examples_directory_exists() -> None:
    assert EXAMPLES_DIR.is_dir()
    assert list(EXAMPLES_DIR.glob("*.py"))


def test_all_examples_compile() -> None:
    for path in EXAMPLES_DIR.glob("*.py"):
        py_compile.compile(str(path), doraise=True)
