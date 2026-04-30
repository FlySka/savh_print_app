from __future__ import annotations

import os
import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Agrega `src` al `sys.path` para imports de test locales."""

    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def _seed_required_env() -> None:
    """Define variables mínimas para importar módulos del proyecto en tests."""

    repo_root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("UPLOAD_DIR", str(repo_root / "data" / "uploads"))


_ensure_src_on_path()
_seed_required_env()