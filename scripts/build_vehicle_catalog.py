"""
Build frontend/data/vehicle_catalog.json from UsedCars.csv.
Brand = first token of `name`; model = remainder (same split as app.py).
"""
from __future__ import annotations

import json
import os

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CSV_PATH = os.path.join(ROOT, "UsedCars.csv")
OUT_PATH = os.path.join(ROOT, "frontend", "data", "vehicle_catalog.json")


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    df["name"] = df["name"].astype(str)
    df["brand"] = df["name"].str.split().str[0]
    df["model"] = df["name"].str.split().str[1:].str.join(" ")
    df = df[df["model"].str.len() > 0]

    brands = sorted(df["brand"].unique().tolist())
    models_by_brand: dict[str, list[str]] = {}
    for b in brands:
        models = sorted(df.loc[df["brand"] == b, "model"].unique().tolist())
        if "Other" not in models:
            models.append("Other")
        else:
            models = [m for m in models if m != "Other"] + ["Other"]
        models_by_brand[b] = models

    payload = {
        "sourceFile": "UsedCars.csv",
        "description": "Brand and model lists derived the same way as app.py: first word = brand, rest = model.",
        "rowCount": int(len(df)),
        "brandCount": len(brands),
        "brands": brands,
        "modelsByBrand": models_by_brand,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Wrote {OUT_PATH} ({len(brands)} brands)")


if __name__ == "__main__":
    main()
