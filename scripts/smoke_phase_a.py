#!/usr/bin/env python3
"""Faz A duman testi: ortak tarama çekirdeği ve skor politikası."""
from __future__ import annotations

import os
import sys

# Proje kökünü path'e ekle (scripts/ altından çalıştırınca)
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> None:
    from scan_pipeline import prepare_symbol_dataframes

    assert callable(prepare_symbol_dataframes)

    from scoring import get_scanner_policy, SCORE_SYMBOL_PRIMARY_KEYS

    p = get_scanner_policy()
    assert "weights" in p
    assert len(SCORE_SYMBOL_PRIMARY_KEYS) >= 10

    print("smoke_phase_a: OK")


if __name__ == "__main__":
    main()
