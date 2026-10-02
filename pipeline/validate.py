from pipeline.columns import PROVENANCE, load_columns

KJ_PER_KCAL = 4.184
BASES = load_columns().bases


def number(value) -> float | None:
    """The cell as a number, or None for blanks and words like 'Trace' or '<0.1'."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_row(row: dict) -> list[str]:
    """Arithmetic sanity checks on numeric cells. Absolute floors stop rounding on tiny values raising false alarms."""
    issues = []
    for base in BASES:
        def get(nutrient: str) -> float | None:
            return number(row.get(f"{nutrient}_{base}"))

        kj, kcal = get("energykJ"), get("energykCal")
        if kj is not None and kcal is not None and abs(kj - KJ_PER_KCAL * kcal) > max(0.03 * kj, 5):
            issues.append(f"error: kJ/kcal mismatch {base}: {kj:g} kJ vs {kcal:g} kcal")
        for part, whole in (("saturates", "fat"), ("sugars", "carbohydrates")):
            p, w = get(part), get(whole)
            if p is not None and w is not None and p > w + 0.05:
                issues.append(f"error: {part} > {whole} {base}: {p:g} > {w:g}")
        protein, carbs, fat = get("protein"), get("carbohydrates"), get("fat")
        if kcal is not None and None not in (protein, carbs, fat):
            estimate = 4 * protein + 4 * carbs + 9 * fat + 2 * (get("fibre") or 0)
            # warn only: alcohol (7 kcal/g) and polyols legitimately break this
            if abs(estimate - kcal) > max(0.15 * kcal, 10):
                issues.append(f"warn: Atwater {base}: stated {kcal:g} kcal, estimated {estimate:.0f}")
    return issues


def duplicate_issues(rows: list[dict],
                     key_cols: tuple[str, ...] = ("Product_Name", "Category", "Cheese", "Crust", "Size", "Serving_Size", "Milk", "region")) -> dict[int, str]:
    def values(r: dict) -> dict:
        return {k: v for k, v in r.items() if k not in PROVENANCE}

    seen: dict[tuple, int] = {}
    out = {}
    for i, r in enumerate(rows):
        key = tuple(r.get(k) for k in key_cols)
        if key in seen and values(rows[seen[key]]) != values(r):
            out[i] = f"error: duplicate of row {seen[key]} with different values"
        seen.setdefault(key, i)
    return out
