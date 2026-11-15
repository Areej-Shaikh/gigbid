"""Small, dependency-free significance tests used by the evaluations."""
import math


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """(z, two-sided p) for H0: p1 == p2, pooled standard error."""
    if not n1 or not n2:
        return 0.0, 1.0
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 0.0, 1.0
    z = (k1 / n1 - k2 / n2) / se
    return z, math.erfc(abs(z) / math.sqrt(2))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the 2x2 table [[a, b], [c, d]] (sum of tables at most as likely)."""
    r1, c1, n = a + b, a + c, a + b + c + d

    def prob(x: int) -> float:
        return math.comb(c1, x) * math.comb(n - c1, r1 - x) / math.comb(n, r1)

    p_obs = prob(a)
    lo, hi = max(0, r1 + c1 - n), min(r1, c1)
    return min(1.0, sum(prob(x) for x in range(lo, hi + 1) if prob(x) <= p_obs * (1 + 1e-9)))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p for paired outcomes; b, c = discordant pair counts."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def min_detectable_effect(p: float, n_per_arm: int, alpha_z: float = 1.96, power_z: float = 0.84) -> float:
    """Smallest absolute difference in proportions detectable with 80% power at alpha 0.05 (two-sided)."""
    if not n_per_arm:
        return float("nan")
    return (alpha_z + power_z) * math.sqrt(2 * p * (1 - p) / n_per_arm)


def cohen_kappa(a: list[int], b: list[int], labels: list[int] | None = None, weights: str | None = None) -> float:
    """Cohen's kappa between two raters; weights=None (exact agreement), "linear" or "quadratic" (ordinal scales)."""
    if len(a) != len(b) or not a:
        raise ValueError("need two equally long, non-empty rating lists")
    labels = labels or sorted(set(a) | set(b))
    idx = {v: i for i, v in enumerate(labels)}
    k, n = len(labels), len(a)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1 / n
    ra = [sum(row) for row in obs]
    rb = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    def w(i: int, j: int) -> float:
        if weights is None:
            return 0.0 if i == j else 1.0
        d = abs(i - j) / max(k - 1, 1)
        return d if weights == "linear" else d * d
    po = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    pe = sum(w(i, j) * ra[i] * rb[j] for i in range(k) for j in range(k))
    return 1.0 if pe == 0 else 1 - po / pe


def fleiss_kappa(ratings: list[list[str]]) -> float:
    """Agreement among a fixed number of raters per item (rows = items, values = category labels)."""
    rows = [r for r in ratings if r]
    if not rows:
        return float("nan")
    n = len(rows[0])
    if n < 2 or any(len(r) != n for r in rows):
        raise ValueError("every item needs the same number (>= 2) of ratings")
    cats = sorted({c for r in rows for c in r})
    counts = [[r.count(c) for c in cats] for r in rows]
    p_i = [(sum(x * x for x in row) - n) / (n * (n - 1)) for row in counts]
    p_bar = sum(p_i) / len(rows)
    p_j = [sum(row[j] for row in counts) / (len(rows) * n) for j in range(len(cats))]
    p_e = sum(p * p for p in p_j)
    return 1.0 if p_e == 1 else (p_bar - p_e) / (1 - p_e)


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test (ties dropped): is one system preferred more often than chance?"""
    return mcnemar_exact(wins, losses)
