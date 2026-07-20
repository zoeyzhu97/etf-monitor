# -*- coding: utf-8 -*-
"""手动导入历史份额CSV: python import_history.py 510300 path/to/file.csv
CSV两列: date,total_shares_yi (表头必需)。用于自动回补失败时的兜底。"""
import csv
import sys
from utils import append_history


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1
    code, path = sys.argv[1], sys.argv[2]
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            append_history(code, row["date"].strip(),
                           float(row["total_shares_yi"]), "manual_import", True)
            n += 1
    print(f"导入 {n} 条 -> data/history/{code}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
