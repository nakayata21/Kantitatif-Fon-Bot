#!/usr/bin/env python3
"""
Günlük BIST takas kümelemesi. Örnek:
  python3 scripts/run_takas_clustering.py
  python3 scripts/run_takas_clustering.py --method gmm --clusters 6
"""
from __future__ import annotations

import argparse
import sys

# Proje kökü
sys.path.insert(0, ".")


def main() -> None:
    p = argparse.ArgumentParser(description="BIST takas özellikleri ile günlük kümeleme")
    p.add_argument("--method", choices=("kmeans", "gmm", "dbscan"), default="kmeans")
    p.add_argument("--clusters", type=int, default=5, help="K-Means / GMM küme sayısı")
    p.add_argument("--date", default=None, help="YYYY-MM-DD (varsayılan: bugün)")
    args = p.parse_args()

    from takas_cluster_db import init_takas_cluster_tables
    from takas_clustering import run_daily_bist_clustering

    init_takas_cluster_tables()
    out = run_daily_bist_clustering(method=args.method, n_clusters=args.clusters, run_date=args.date)
    print(out)


if __name__ == "__main__":
    main()
