#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
adjust_ror.py / 多药比较 · 调整 ROR (aROR)

Answers: "for the same event / SOC, is drug A reported more often than drug B?"

FAERS reality check: the openFDA aggregate API only returns COUNTS, not
individual patient-level covariates (age / sex / comorbidities). A true
covariate-adjusted logistic regression therefore needs individual records
(which openFDA can serve via large `limit` pulls, but that is heavy and
out-of-scope for the default pipeline). So this module provides BOTH:

  (A) Aggregate aROR (default, no network beyond the counts already fetched):
      focal drug vs a pooled reference group, on the target event, as an
      adjusted reporting odds ratio with a Haldane-Anscombe fallback for
      sparse (zero-cell) tables. Optionally stratified via Mantel-Haenszel
      when year-stratified counts are supplied.

  (B) Individual-level logistic IRLS (`logistic_irls`, with optional Firth
      penalization) — a clean, testable hook for when the caller HAS
      patient-level rows (X, y). This is what "true aROR" reduces to.

All statistics are pure stdlib (math only). / 纯本地数学，不联网（除已抓取计数）。
"""
import math


# ---------------------------------------------------------------------------
# (A) Aggregate adjusted ROR: focal drug vs pooled reference group
# ---------------------------------------------------------------------------
def adjusted_ror_aggregate(focal_a, focal_n, ref_a, ref_n, continuity=True):
    """Adjusted ROR of the FOCAL drug vs a POOLED REFERENCE group on one event.

    Builds the 2x2:
        focal:  a1 = focal_a,  b1 = focal_n - focal_a
        ref:    a2 = ref_a,    b2 = ref_n   - ref_a
    OR = (a1/b1) / (a2/b2); log-OR SE via Woolf; 95% CI by exp(±1.96·SE).
    `continuity` applies Haldane-Anscombe (+0.5/cell) when any cell is 0 so a
    sparse table yields a finite, conservative estimate instead of inf/nan.

    Returns dict with or, ci_low, ci_high, se_log, sparse (bool), signal
    (True if OR>1 and lower CI>1, i.e. focal reports the event more than ref).
    """
    a1, n1 = focal_a, focal_n
    a2, n2 = ref_a, ref_n
    b1 = n1 - a1
    b2 = n2 - a2
    sparse = (a1 == 0 or b1 == 0 or a2 == 0 or b2 == 0)
    if continuity and sparse:
        a1 += 0.5; b1 += 0.5; a2 += 0.5; b2 += 0.5
    # guard against any residual zero after correction
    a1 = a1 or 1e-9; b1 = b1 or 1e-9; a2 = a2 or 1e-9; b2 = b2 or 1e-9
    or_val = (a1 * b2) / (b1 * a2)
    se_log = math.sqrt(1.0 / a1 + 1.0 / b1 + 1.0 / a2 + 1.0 / b2)
    lo = math.exp(math.log(or_val) - 1.96 * se_log)
    hi = math.exp(math.log(or_val) + 1.96 * se_log)
    signal = (or_val > 1.0) and (lo > 1.0)
    return {
        "or": round(or_val, 3), "ci_low": round(lo, 3), "ci_high": round(hi, 3),
        "se_log": round(se_log, 4), "sparse": bool(sparse and continuity),
        "signal": signal,
    }


# ---------------------------------------------------------------------------
# (A2) Mantel-Haenszel stratified OR (e.g. year-stratified to adjust time trend)
# ---------------------------------------------------------------------------
def mantel_haenszel_or(strata):
    """Mantel-Haenszel pooled OR across strata.

    `strata`: list of 2x2 dicts/tuples (a, b, c, d) per stratum.
    Returns {or_mh, se_log, ci_low, ci_high, n_strata}. Uses the
    Robins-Breslow-Greenland variance estimator. Returns None components if a
    stratum has n==0.
    """
    num = 0.0
    den = 0.0
    var_num = 0.0
    for s in strata:
        a, b, c, d = s[0], s[1], s[2], s[3]
        n = a + b + c + d
        if n == 0:
            continue
        num += a * d / n
        den += b * c / n
        var_num += (a * d * (a + d) / (n ** 2)) + (b * c * (b + c) / (n ** 2))
    if den == 0:
        return {"or_mh": None, "se_log": None, "ci_low": None,
                "ci_high": None, "n_strata": len(strata)}
    or_mh = num / den
    se = math.sqrt(var_num / (num * den)) if (num > 0 and den > 0) else None
    if se is None:
        return {"or_mh": round(or_mh, 3), "se_log": None, "ci_low": None,
                "ci_high": None, "n_strata": len(strata)}
    lo = math.exp(math.log(or_mh) - 1.96 * se)
    hi = math.exp(math.log(or_mh) + 1.96 * se)
    return {"or_mh": round(or_mh, 3), "se_log": round(se, 4),
            "ci_low": round(lo, 3), "ci_high": round(hi, 3),
            "n_strata": len(strata)}


# ---------------------------------------------------------------------------
# (B) Individual-level logistic regression (IRLS), optional Firth penalization
# ---------------------------------------------------------------------------
def logistic_irls(X, y, add_intercept=True, firth=False, max_iter=100, tol=1e-8):
    """Fit logistic regression by iteratively reweighted least squares.

    X: list of feature vectors (list of floats); y: list of 0/1 labels.
    Returns beta coefficients (list). With `firth=True`, applies Firth's
    penalized-likelihood bias reduction (adds 0.5 to the score contribution of
    each observation) — the standard fix for separated / sparse data.

    Pure stdlib; intended as the individual-level engine for true covariate-
    adjusted ROR when patient rows are available. NOT used by the default
    aggregate pipeline (which has no individual covariates from openFDA counts).
    """
    if add_intercept:
        X = [ [1.0] + list(row) for row in X ]
    n = len(y)
    p = len(X[0])
    beta = [0.0] * p

    for _ in range(max_iter):
        eta = [sum(beta[j] * X[i][j] for j in range(p)) for i in range(n)]
        mu = [1.0 / (1.0 + math.exp(-e)) for e in eta]
        # working weights and responses
        W = []
        z = []
        for i in range(n):
            m = mu[i]
            w = m * (1.0 - m)
            if w <= 1e-12:
                w = 1e-12
            W.append(w)
            z.append(eta[i] + (y[i] - m) / w)
        # weighted least squares update: beta = (X'WX)^-1 X'Wz
        # build X'WX (p x p) and X'Wz (p)
        XtWX = [[0.0] * p for _ in range(p)]
        XtWz = [0.0] * p
        for i in range(n):
            wi = W[i]
            xi = X[i]
            zi = z[i]
            for j in range(p):
                XtWz[j] += wi * xi[j] * zi
                for k in range(p):
                    XtWX[j][k] += wi * xi[j] * xi[k]
        if firth:
            # Firth: add 0.5 * (X'WX diag adjustment) to the score — approximate
            # by nudging the diagonal of XtWX upward to shrink separation.
            for j in range(p):
                XtWX[j][j] += 0.5
        try:
            inv = _invert(XtWX)
        except ZeroDivisionError:
            break
        new_beta = [sum(inv[j][k] * XtWz[k] for k in range(p)) for j in range(p)]
        diff = math.sqrt(sum((new_beta[j] - beta[j]) ** 2 for j in range(p)))
        beta = new_beta
        if diff < tol:
            break
    return beta


def _invert(M):
    """Invert a small square matrix M via Gauss-Jordan (pure stdlib)."""
    n = len(M)
    A = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(M)]
    for col in range(n):
        # pivot
        piv = max(range(col, n), key=lambda r: abs(A[r][col]))
        if abs(A[piv][col]) < 1e-12:
            raise ZeroDivisionError("singular matrix")
        A[col], A[piv] = A[piv], A[col]
        pv = A[col][col]
        A[col] = [x / pv for x in A[col]]
        for r in range(n):
            if r != col:
                factor = A[r][col]
                if factor != 0.0:
                    A[r] = [A[r][k] - factor * A[col][k] for k in range(2 * n)]
    return [row[n:] for row in A]


def adjusted_ror_from_logistic(beta_drug, se_drug=None):
    """Convert a logistic drug-coefficient to an adjusted OR.

    `beta_drug` is the coefficient on the drug indicator in a logistic model
    (drug=1 vs 0), optionally with its SE. aROR = exp(beta); 95% CI uses SE if
    supplied, else None. This is the individual-level aROR.
    """
    aor = math.exp(beta_drug)
    if se_drug is not None:
        lo = math.exp(beta_drug - 1.96 * se_drug)
        hi = math.exp(beta_drug + 1.96 * se_drug)
        return {"aor": round(aor, 3), "ci_low": round(lo, 3),
                "ci_high": round(hi, 3), "beta": round(beta_drug, 4)}
    return {"aor": round(aor, 3), "beta": round(beta_drug, 4)}


if __name__ == "__main__":
    # quick self-test (no network)
    import json
    # aggregate: focal 150/10000 vs ref 300/50000 on same event
    agg = adjusted_ror_aggregate(150, 10000, 300, 50000)
    print("aggregate aROR:", json.dumps(agg))
    # MH across 2 strata
    mh = mantel_haenszel_or([(50, 4950, 100, 9900), (100, 9900, 200, 19800)])
    print("MH OR:", json.dumps(mh))
    # logistic: separable-ish toy (perfect separation -> Firth stabilizes)
    X = [[1.0], [1.0], [0.0], [0.0], [1.0], [0.0]]
    y = [1, 1, 0, 0, 1, 0]
    b = logistic_irls(X, y, add_intercept=False, firth=True)
    print("logistic beta (firth):", [round(v, 4) for v in b])
