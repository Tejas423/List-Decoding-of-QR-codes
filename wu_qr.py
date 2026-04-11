#!/usr/bin/env python3
"""
wu_list_decode_gf256.py

Wu's rational curve-fitting list decoder for Reed-Solomon codes
over GF(2^8), using QR-code-style generator-polynomial encoding.

Reference:
  "New List Decoding Algorithms for Reed-Solomon and BCH Codes"
  Yingquan Wu, ISIT 2007.

Run:  python wu_list_decode_gf256.py
"""

import random, math, numpy as np
import itertools

# ═══════════════════════════════════════════════════════════════════════════════
#  GF(2^8) Arithmetic  —  same field as QR codes
#  Primitive polynomial: x^8 + x^4 + x^3 + x^2 + 1  (0x11D)
#  Primitive element:    α = 2  (α^255 = 1)
# ═══════════════════════════════════════════════════════════════════════════════

PRIM_POLY = 0x11D
GF = 256
ALPHA = 2

_exp = [0] * 512
_log = [0] * 256

_x = 1
for _i in range(255):
    _exp[_i] = _x
    _log[_x] = _i
    _x <<= 1
    if _x & 256:
        _x ^= PRIM_POLY
for _i in range(255, 512):
    _exp[_i] = _exp[_i - 255]

# NumPy lookup tables for vectorized GF(2^8) operations
EXP_NP = np.array(_exp[:512], dtype=np.int32)
LOG_NP = np.array(_log[:256], dtype=np.int32)

# Precomputed alpha power tables (avoid repeated gf_pow calls)
_alpha_pow = [1] * 256
for _i in range(1, 256):
    _alpha_pow[_i] = _exp[_i % 255]

_alpha_neg = [1] * 256
for _i in range(1, 256):
    _alpha_neg[_i] = _exp[(255 - _i) % 255]

def gf_add(a, b):  return a ^ b
def gf_sub(a, b):  return a ^ b          # char 2: sub = add
def gf_neg(a):     return a              # char 2: -a = a

def gf_mul(a, b):
    if a == 0 or b == 0: return 0
    return _exp[_log[a] + _log[b]]

def gf_div(a, b):
    if b == 0: raise ZeroDivisionError
    if a == 0: return 0
    return _exp[(_log[a] - _log[b]) % 255]

def gf_inv(a):
    if a == 0: raise ZeroDivisionError
    return _exp[255 - _log[a]]

def gf_pow(a, n):
    if n == 0: return 1
    if a == 0: return 0
    return _exp[(_log[a] * (n % 255)) % 255]

# ═══════════════════════════════════════════════════════════════════════════════
#  Polynomial ops over GF(2^8)
#  Representation: [a0, a1, ..., an] = a0 + a1*x + ... + an*x^n
# ═══════════════════════════════════════════════════════════════════════════════

def ps(c):
    c = list(c)
    while len(c) > 1 and c[-1] == 0: c.pop()
    return c

def pdeg(c):
    c = ps(c)
    return -1 if c == [0] else len(c) - 1

def padd(a, b):
    n = max(len(a), len(b))
    return ps([(a[i] if i < len(a) else 0) ^ (b[i] if i < len(b) else 0) for i in range(n)])

psub = padd   # char 2

def pmul(a, b):
    if a == [0] or b == [0]: return [0]
    b_arr = np.array(b, dtype=np.int32)
    b_nz = b_arr != 0
    out = np.zeros(len(a) + len(b) - 1, dtype=np.int32)
    for i, ai in enumerate(a):
        if ai == 0: continue
        products = np.zeros(len(b), dtype=np.int32)
        products[b_nz] = EXP_NP[LOG_NP[ai] + LOG_NP[b_arr[b_nz]]]
        out[i:i+len(b)] ^= products
    return ps(out.tolist())

def pscalar(a, c):
    if c == 0 or a == [0]: return [0]
    return ps([gf_mul(x, c) for x in a])

def peval(a, x):
    acc = 0
    for i in range(len(a) - 1, -1, -1):
        acc = gf_add(gf_mul(acc, x), a[i])
    return acc

def pmod(a, m):
    a, m = ps(list(a)), ps(m)
    il = gf_inv(m[-1])
    while len(a) >= len(m) and a != [0]:
        c = gf_mul(a[-1], il)
        s = len(a) - len(m)
        for k in range(len(m)):
            a[s + k] ^= gf_mul(m[k], c)
        a = ps(a)
    return a

def pgcd(a, b):
    a, b = ps(a), ps(b)
    while b != [0]: a, b = b, pmod(a, b)
    if a != [0]: a = pscalar(a, gf_inv(a[-1]))
    return a

# ═══════════════════════════════════════════════════════════════════════════════
#  RS Code — QR-code-style generator-polynomial encoding
# ═══════════════════════════════════════════════════════════════════════════════

_rs_gen_cache = {}

def rs_generator(nsym):
    """g(x) = prod_{i=0}^{nsym-1} (x - alpha^i).  In char 2, - = +."""
    if nsym in _rs_gen_cache:
        return list(_rs_gen_cache[nsym])
    g = [1]
    for i in range(nsym):
        g = pmul(g, [_alpha_pow[i], 1])
    _rs_gen_cache[nsym] = g[:]
    return g

def rs_encode(n, k, msg):
    """
    Systematic encoding:
      c(x) = m(x)*x^{n-k} + (m(x)*x^{n-k} mod g(x))
    Returns codeword [parity_0, ..., parity_{n-k-1}, msg_0, ..., msg_{k-1}].
    """
    nsym = n - k
    g = rs_generator(nsym)
    # m(x) * x^{n-k}
    rem = [0] * nsym + list(msg[:k])
    # Polynomial long division: process from highest degree to lowest
    for i in range(k - 1, -1, -1):
        coeff = rem[nsym + i]
        if coeff == 0: continue
        for j in range(nsym + 1):
            rem[i + j] ^= gf_mul(g[j], coeff)
    # Codeword = remainder (parity) + message
    codeword = rem[:nsym] + list(msg[:k])
    return codeword

def rs_syndromes(n, k, received):
    """S_j = R(alpha^j) for j = 0, ..., n-k-1.  All zero for valid codewords."""
    nsym = n - k
    return [peval(received, _alpha_pow[j]) for j in range(nsym)]

# ═══════════════════════════════════════════════════════════════════════════════
#  Berlekamp-Massey over GF(2^8)
# ═══════════════════════════════════════════════════════════════════════════════

def berlekamp_massey(S):
    """
    BM on syndromes S = [S_0, S_1, ..., S_{N-1}].
    Returns (Lambda, B) with L_Lambda + L_B = N.
    """
    N = len(S); C = [1]; B = [1]; L = 0; dp = 1
    for r in range(N):
        delta = S[r]
        for i in range(1, L + 1):
            if i < len(C) and r - i >= 0:
                delta ^= gf_mul(C[i], S[r - i])
        T = C[:]
        if delta != 0:
            sc = gf_mul(delta, gf_inv(dp))
            xB = [0] + B
            xBs = [gf_mul(c, sc) for c in xB]
            ml = max(len(C), len(xBs))
            C = [(C[i] if i < len(C) else 0) ^ (xBs[i] if i < len(xBs) else 0) for i in range(ml)]
            C = ps(C)
            if 2 * L <= r:
                B = T[:]; L = r + 1 - L; dp = delta
            else:
                B = [0] + B
        else:
            B = [0] + B
    C = ps(C); B = ps(B)
    if C[0] != 0:
        iv = gf_inv(C[0])
        C = [gf_mul(c, iv) for c in C]
    return ps(C), ps(B)

# ═══════════════════════════════════════════════════════════════════════════════
#  Nullspace over GF(2^8) via Gaussian elimination
# ═══════════════════════════════════════════════════════════════════════════════

def nullspace(A):
    m = len(A)
    if m == 0: return []
    nc = len(A[0])
    M = np.array(A, dtype=np.int32)
    row = 0; pivs = []
    for col in range(nc):
        nz = np.nonzero(M[row:, col])[0]
        if len(nz) == 0: continue
        piv = row + nz[0]
        if piv != row:
            M[[row, piv]] = M[[piv, row]]
        # Scale pivot row: M[row] *= gf_inv(M[row, col])
        iv = gf_inv(int(M[row, col]))
        pr = M[row].copy()
        nz_pr = pr != 0
        M[row] = 0
        M[row, nz_pr] = EXP_NP[LOG_NP[pr[nz_pr]] + LOG_NP[iv]]
        # Eliminate all other rows with non-zero entry in this column
        factors = M[:, col].copy()
        factors[row] = 0
        nz_rows = np.nonzero(factors)[0]
        if len(nz_rows) > 0:
            piv_nz_cols = np.nonzero(M[row])[0]
            for j in piv_nz_cols:
                log_pv = LOG_NP[int(M[row, j])]
                M[nz_rows, j] ^= EXP_NP[LOG_NP[factors[nz_rows]] + log_pv]
        pivs.append(col); row += 1
        if row == m: break
    free = [c for c in range(nc) if c not in pivs]
    if not free: return []
    basis = []
    for fc in free:
        v = [0] * nc; v[fc] = 1
        for idx, pc in enumerate(pivs):
            v[pc] = int(M[idx, fc])
        basis.append(v)
    return basis

# ═══════════════════════════════════════════════════════════════════════════════
#  Interpolation system — (1, w)-weighted, multiplicity m
#  Binomial coefficients mod 2 via Lucas' theorem
# ═══════════════════════════════════════════════════════════════════════════════

def binom2(n, k):
    """C(n, k) mod 2.  By Lucas' theorem: 1 iff k is a submask of n in binary."""
    if k < 0 or k > n: return 0
    return 1 if (k & n) == k else 0

def monomial_list(Ly, LQ, w):
    mons = []
    for j in range(Ly + 1):
        mx = LQ - w * j
        if mx < 0: continue
        for i in range(mx + 1):
            mons.append((i, j))
    return mons

def build_interp(xs, ys, is_inf, m, mons, Ly):
    nm = len(mons); rows = []
    if nm == 0: return rows
    mi = max(i for i, _ in mons)
    mj = max(j for _, j in mons)
    mon_i = np.array([i for i, _ in mons], dtype=np.int32)
    mon_j = np.array([j for _, j in mons], dtype=np.int32)
    # Precompute binom2 masks (Lucas: C(n,k) mod 2 = 1 iff k is submask of n)
    fin_masks = {}
    for a in range(m):
        for b in range(m - a):
            fin_masks[(a, b)] = np.array(
                [(i >= a and j >= b and (a & i) == a and (b & j) == b) for i, j in mons], dtype=bool)
    inf_masks = {}
    for a in range(m):
        for b in range(m - a):
            if b > Ly: continue
            jt = Ly - b
            inf_masks[(a, b)] = np.array(
                [(j == jt and i >= a and (a & i) == a) for i, j in mons], dtype=bool)
    for ti in range(len(xs)):
        xt = xs[ti]
        if not is_inf[ti]:
            yt = ys[ti]
            px = np.ones(mi + 1, dtype=np.int32)
            for e in range(1, mi + 1): px[e] = gf_mul(int(px[e-1]), xt)
            py = np.ones(mj + 1, dtype=np.int32)
            for e in range(1, mj + 1): py[e] = gf_mul(int(py[e-1]), yt)
            for a in range(m):
                for b in range(m - a):
                    mask = fin_masks[(a, b)]
                    row = np.zeros(nm, dtype=np.int32)
                    if np.any(mask):
                        pxv = px[mon_i[mask] - a]
                        pyv = py[mon_j[mask] - b]
                        both_nz = (pxv != 0) & (pyv != 0)
                        if np.any(both_nz):
                            vals = np.zeros(int(np.sum(mask)), dtype=np.int32)
                            vals[both_nz] = EXP_NP[LOG_NP[pxv[both_nz]] + LOG_NP[pyv[both_nz]]]
                            row[mask] = vals
                    rows.append(row.tolist())
        else:
            px = np.ones(mi + 1, dtype=np.int32)
            for e in range(1, mi + 1): px[e] = gf_mul(int(px[e-1]), xt)
            for a in range(m):
                for b in range(m - a):
                    if b > Ly: continue
                    mask = inf_masks[(a, b)]
                    row = np.zeros(nm, dtype=np.int32)
                    if np.any(mask):
                        row[mask] = px[mon_i[mask] - a]
                    rows.append(row.tolist())
    return rows

def vec_to_Q(vec, mons, Ly):
    mx = [0] * (Ly + 1)
    for i, j in mons:
        if j <= Ly and i > mx[j]: mx[j] = i
    Q = [[0] * (mx[j] + 1) for j in range(Ly + 1)]
    for c, (i, j) in zip(vec, mons):
        if j <= Ly: Q[j][i] ^= c
    return [ps(Qj) for Qj in Q]

# ═══════════════════════════════════════════════════════════════════════════════
#  Hensel Lifting (Newton-Raphson for power series)
#
#  Replaces RR's exponential tree search with quadratic convergence:
#    - Find initial roots at depth 0: scan GF(256) once
#    - For each root, DOUBLE precision each step: K terms in O(log K) steps
#    - No branching after step 0
#
#  Complexity: O(#roots × K × log K × poly_ops)
#  vs RR:     O(256^branching × K × deg_y)    ← can explode
# ═══════════════════════════════════════════════════════════════════════════════

def _ptrunc(a, m):
    """Truncate polynomial to mod x^m (keep first m coefficients)."""
    if m <= 0: return [0]
    return ps((a + [0] * m)[:m])

def _pmul_mod(a, b, m):
    """Multiply polynomials mod x^m (numpy-vectorized inner loop)."""
    if a == [0] or b == [0]: return [0]
    b_arr = np.array(b, dtype=np.int32)
    b_nz = b_arr != 0
    out = np.zeros(m, dtype=np.int32)
    for i, ai in enumerate(a):
        if ai == 0 or i >= m: continue
        jmax = min(len(b), m - i)
        if jmax <= 0: continue
        b_slice = b_arr[:jmax]
        nz = b_nz[:jmax]
        products = np.zeros(jmax, dtype=np.int32)
        products[nz] = EXP_NP[LOG_NP[ai] + LOG_NP[b_slice[nz]]]
        out[i:i+jmax] ^= products
    return ps(out.tolist())

def _pinv_mod(f, m):
    """
    Compute f(x)^{-1} mod x^m using Newton iteration.
    In char 2: g_{i+1} = f * g_i^2 mod x^{2^{i+1}}
    Requires f(0) != 0.
    """
    if f == [0] or f[0] == 0:
        return None  # not invertible
    g = [gf_inv(f[0])]  # g_0 = f(0)^{-1}, correct mod x^1
    prec = 1
    while prec < m:
        new_prec = min(prec * 2, m)
        # g = f * g^2 mod x^{new_prec}
        g2 = _pmul_mod(g, g, new_prec)
        g = _pmul_mod(f, g2, new_prec)
        prec = new_prec
    return _ptrunc(g, m)

def _Q_eval_series(Q, s, m):
    """Evaluate Q(x, s(x)) mod x^m, where Q = [Q_0(x), Q_1(x), ..., Q_Ly(x)]."""
    result = _ptrunc(Q[0], m) if Q[0] != [0] else [0]
    s_pow = [1]  # s^0 = 1
    for j in range(1, len(Q)):
        s_pow = _pmul_mod(s_pow, s, m)  # s^j
        if Q[j] != [0]:
            term = _pmul_mod(Q[j], s_pow, m)
            result = padd(result, term)
    return _ptrunc(result, m)

def _Qy_eval_series(Q, s, m):
    """
    Evaluate dQ/dy(x, s(x)) mod x^m.
    In char 2: dQ/dy = sum_{odd j} Q_j(x) * y^{j-1}
    (even j terms vanish because j * coeff = 0 in char 2)
    """
    result = [0]
    s_pow = [1]  # s^0
    for j in range(1, len(Q)):
        if j % 2 == 1:  # only odd j contributes in char 2
            if Q[j] != [0]:
                # j * Q_j * s^{j-1} = Q_j * s^{j-1} (since j is odd, j mod 2 = 1)
                term = _pmul_mod(Q[j], s_pow, m)
                result = padd(result, term)
        s_pow = _pmul_mod(s_pow, s, m)  # s^j (for next iteration, s^{j-1+1} = s^j)
    return _ptrunc(result, m)

def hensel_series(Q, K, max_roots=64):
    """
    Find power series roots of Q(x, y) to precision K using Hensel lifting.
    
    Algorithm:
      1. Find roots of Q(0, y) = 0 by scanning GF(256)
      2. For each root y0, Newton-lift: s = y0 + ... to K terms
         s_{new} = s + Q(x,s) * Q_y(x,s)^{-1} mod x^{2m}
         (In char 2, subtraction = addition)
      3. Verify Q(x, s) ≡ 0 mod x^K
    
    Returns list of K-length coefficient lists.
    """
    Ly = len(Q) - 1
    if Ly < 0:
        return []

    # Step 1: Find roots at x=0 (scan field once)
    P0 = [Qj[0] if Qj != [0] else 0 for Qj in Q]
    initial_roots = []
    for y in range(GF):
        val = 0; py = 1
        for c in P0:
            val ^= gf_mul(c, py)
            py = gf_mul(py, y)
        if val == 0:
            initial_roots.append(y)
    if len(initial_roots) > max_roots:
        initial_roots = initial_roots[:max_roots]

    results = []
    for y0 in initial_roots:
        # Step 2: Hensel lift from s = [y0] to K terms
        s = [y0]  # known mod x^1
        prec = 1

        success = True
        while prec < K:
            new_prec = min(prec * 2, K)

            # Evaluate Q(x, s) mod x^{new_prec}
            Qs = _Q_eval_series(Q, s, new_prec)

            # Check if already zero
            if all(c == 0 for c in _ptrunc(Qs, new_prec)):
                # Already a root to this precision, pad with zeros
                s = (s + [0] * new_prec)[:new_prec]
                prec = new_prec
                continue

            # Evaluate Q_y(x, s) mod x^{new_prec}
            Qys = _Qy_eval_series(Q, s, new_prec)

            # Need Q_y(x, s) to be invertible (non-zero constant term)
            if Qys == [0] or Qys[0] == 0:
                # Q_y vanishes — Hensel can't lift (multiple root)
                # Fall back: pad with zeros (partial result)
                success = False
                break

            # Compute Q_y^{-1} mod x^{new_prec}
            Qys_inv = _pinv_mod(Qys, new_prec)
            if Qys_inv is None:
                success = False
                break

            # Newton step: s_new = s + Q(x,s) * Q_y(x,s)^{-1} mod x^{new_prec}
            # (In char 2: + and - are the same)
            delta = _pmul_mod(Qs, Qys_inv, new_prec)
            s_new = padd((s + [0] * new_prec)[:new_prec], _ptrunc(delta, new_prec))
            s = _ptrunc(s_new, new_prec)
            prec = new_prec

        # Pad to K terms
        s = (s + [0] * K)[:K]

        # Step 3: Verify Q(x, s) ≡ 0 mod x^K
        Qs_final = _Q_eval_series(Q, s, K)
        if all(c == 0 for c in _ptrunc(Qs_final, K)):
            results.append(s)

    # Dedup
    seen = set(); uniq = []
    for s in results:
        key = tuple(s)
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return uniq

def rr_series(Q, K, max_br=256):
    Ly = len(Q) - 1; results = []; stack = [(Q, [], 0)]
    while stack and len(results) < max_br:
        Qc, pre, dep = stack.pop()
        if dep >= K: results.append(pre[:K]); continue
        P0 = [Qj[0] if Qj != [0] else 0 for Qj in Qc]
        # Find roots of P0 as univariate poly over GF(256)
        roots = []
        for y in range(GF):
            val = 0; py = 1
            for c in P0:
                val ^= gf_mul(c, py)
                py = gf_mul(py, y)
            if val == 0: roots.append(y)
        for c in roots:
            if len(results) >= max_br: break
            np2 = pre + [c]
            if dep + 1 >= K: results.append(np2[:K]); continue
            Qn = _Qshift(Qc, c)
            if Qn is None: results.append(np2 + [0] * (K - len(np2))); continue
            stack.append((Qn, np2, dep + 1))
    seen = set(); uniq = []
    for s in results:
        # Keep full K-length series — trailing zeros are meaningful for BM recovery
        s = (s + [0] * K)[:K]
        key = tuple(s)
        if key not in seen: seen.add(key); uniq.append(s)
    return uniq

def _Qshift(Q, c):
    """Q(x, c + x*y) / x^v"""
    Ly = len(Q) - 1
    # Binomial and power tables (mod 2 for binomials)
    pc = [1] * (Ly + 1)
    for e in range(1, Ly + 1): pc[e] = gf_mul(pc[e-1], c)
    S = []
    for r in range(Ly + 1):
        Sr = [0]
        for j in range(r, Ly + 1):
            bv = binom2(j, r)
            if bv == 0: continue
            cf = pc[j - r]
            if cf: Sr = padd(Sr, pscalar(Q[j], cf))
        S.append(Sr)
    minv = float('inf')
    for r in range(Ly + 1):
        if S[r] == [0]: continue
        v = 0
        while v < len(S[r]) and S[r][v] == 0: v += 1
        if v < len(S[r]) and r + v < minv: minv = r + v
    if minv == float('inf'): return None
    v = minv; Qn = []
    for r in range(Ly + 1):
        sh = v - r
        if sh < 0: Qn.append([0] * (-sh) + S[r])
        elif sh == 0: Qn.append(S[r][:])
        else: Qn.append(S[r][sh:] if sh < len(S[r]) else [0])
        Qn[-1] = ps(Qn[-1])
    while len(Qn) > 1 and Qn[-1] == [0]: Qn.pop()
    if all(q == [0] for q in Qn): return None
    return Qn

# ═══════════════════════════════════════════════════════════════════════════════
#  Parameter computation
# ═══════════════════════════════════════════════════════════════════════════════

def wu_params(n, k, L_Lam, L_B, t=None):
    d = n - k + 1; t0 = d // 2; L_xB = L_B + 1; w = L_Lam - L_xB
    bnd = n - math.sqrt(n * (k - 1))
    tm = int(math.floor(bnd - 1e-9)) if t is None else min(t, int(math.floor(bnd - 1e-9)))
    tm = max(tm, t0 + 1); gap = bnd - tm
    m_start = int(math.ceil((tm - t0) / gap)) if gap > 1e-9 else 100
    m_start = max(m_start, 1)
    while (tm * m_start + tm - t0) ** 2 <= 2 * n * m_start * (m_start + 1) * (tm - t0):
        m_start += 1
        if m_start > 500:  # safety cap: prevents infinite loop when gap <= 0
            break
    Ly_den = 2 * (tm - t0)
    best = None
    for m in range(m_start, m_start + 60):
        if n * m * (m + 1) // 2 > 800: break
        Ly_opt = (tm * m - tm + t0) / Ly_den if Ly_den > 0 else 1
        for Ly in range(max(1, int(Ly_opt) - 1), int(Ly_opt) + 3):
            LQ = tm * m - 1 - (tm - L_Lam) * Ly; LQ = max(LQ, 0)
            if (tm - L_Lam) * Ly + LQ >= tm * m: continue
            nu = 0
            for j in range(Ly + 1):
                mx = LQ - w * j
                if mx >= 0: nu += mx + 1
            nc = n * m * (m + 1) // 2
            if nu > nc:
                if best is None or m < best[0]:
                    best = (m, nu - nc, Ly, LQ)
        if best is not None: break
    if best is not None:
        m, _, Ly, LQ = best
    else:
        m = m_start
        Ly = max(1, (tm * m - tm + t0) // Ly_den if Ly_den > 0 else 1)
        LQ = Ly * (tm - L_xB) + tm - t0 - 1; LQ = max(LQ, 0)
    Ls = max(3 * tm - 2 * t0 - L_Lam, 4 * (tm - t0), 2)
    return dict(t=tm, t0=t0, m=m, Ly=Ly, LQ=LQ, w=w, Ls=Ls, L_xB=L_xB, ok=best is not None)

# ═══════════════════════════════════════════════════════════════════════════════
#  Chien search via register recurrence (replaces naive Horner evaluation)
# ═══════════════════════════════════════════════════════════════════════════════

def chien_search(poly, n):
    """Find positions i where poly(alpha^{-i}) = 0 using register recurrence."""
    deg = pdeg(poly)
    if deg <= 0:
        return []
    coeffs = (poly + [0] * (deg + 1))[:deg + 1]
    regs = np.array(coeffs, dtype=np.int32)
    mults = np.array([_alpha_neg[j] for j in range(deg + 1)], dtype=np.int32)
    # Precompute log of multipliers (all non-zero since alpha is primitive)
    mult_logs = LOG_NP[mults]
    err_pos = []
    for i in range(n):
        # Evaluate: XOR all registers = poly(alpha^{-i})
        val = int(np.bitwise_xor.reduce(regs))
        if val == 0:
            err_pos.append(i)
        # Update: regs[j] *= alpha^{-j} (vectorized)
        nz = regs != 0
        new_regs = np.zeros_like(regs)
        new_regs[nz] = EXP_NP[LOG_NP[regs[nz]] + mult_logs[nz]]
        regs = new_regs
    return err_pos

# ═══════════════════════════════════════════════════════════════════════════════
#  Recovery: series → (lambda, b) → Lambda* → decode
# ═══════════════════════════════════════════════════════════════════════════════

def recover_from_series(n, k, series, Lambda, B, L_Lam, L_xB, t, t0, received):
    xB = [0] + B; results = []
    pairs = []
    # Method A: BM on subsequence
    start = max(0, t - L_xB + 1); bm_len = 2 * (t - L_Lam)
    if bm_len > 0 and start + bm_len <= len(series):
        sub = series[start:start + bm_len]
        lam, _ = berlekamp_massey(sub)
        trunc = max(t - L_xB + 1, pdeg(lam) + 1)
        b2 = pmul(series[:trunc], lam); b2 = ps(b2[:trunc])
        pairs.append((lam, b2))
    # Method B: BM on full
    lam2, _ = berlekamp_massey(series)
    trunc2 = max(pdeg(lam2) + 1, 1)
    b3 = pmul(series[:trunc2], lam2); b3 = ps(b3[:trunc2])
    pairs.append((lam2, b3))
    # Method C: Padé
    pairs.extend(pade_approx(series, max(t - L_xB, 1), max(t - L_Lam, 1)))

    for lam, b_poly in pairs:
        Lstar = padd(pmul(Lambda, lam), pmul(xB, b_poly))
        Lstar = ps(Lstar)
        if Lstar == [0]: continue
        if Lstar[0] != 0:
            iv = gf_inv(Lstar[0]); Lstar = [gf_mul(c, iv) for c in Lstar]
        # Chien search using register recurrence
        err_pos = chien_search(Lstar, n)
        if len(err_pos) != pdeg(Lstar) or len(err_pos) > t or len(err_pos) == 0:
            continue
        msg = decode_from_positions(n, k, err_pos, received)
        if msg is not None: results.append(msg)
    return results

def pade_approx(series, max_dl, max_db):
    Ls = len(series) - 1; mod_p = [0] * (Ls + 1) + [1]
    rp, rc = mod_p[:], ps(series[:]); tp, tc = [0], [1]; results = []
    while rc != [0]:
        if len(rp) < len(rc): break
        q = [0]; rem = rp[:]; il = gf_inv(rc[-1])
        while len(rem) >= len(rc) and rem != [0]:
            c = gf_mul(rem[-1], il); sh = len(rem) - len(rc)
            q = padd(q, [0] * sh + [c])
            for kk in range(len(rc)):
                rem[sh + kk] ^= gf_mul(rc[kk], c)
            rem = ps(rem)
        tn = psub(tp, pmul(q, tc))
        lam = ps(tn); b_c = ps(rem)
        if 0 <= pdeg(lam) <= max_dl and pdeg(b_c) <= max_db:
            g = pgcd(lam, b_c)
            if pdeg(g) == 0:
                if lam[0] != 0:
                    iv = gf_inv(lam[0])
                    lam = [gf_mul(c2, iv) for c2 in lam]
                    b_c = [gf_mul(c2, iv) for c2 in b_c]
                results.append((ps(lam), ps(b_c)))
        if pdeg(rem) <= max_db: break
        rp, rc = rc, rem; tp, tc = tc, tn
    return results

def decode_from_positions(n, k, err_pos, received):
    """Given error positions, solve for error values and decode."""
    nsym = n - k; ne = len(err_pos)
    if ne == 0:
        syns = rs_syndromes(n, k, received)
        if all(s == 0 for s in syns): return extract_message(n, k, received)
        return None
    syns = rs_syndromes(n, k, received)
    # Build syndrome matrix: S_j = sum e_l * X_l^j
    # where X_l = alpha^{err_pos[l]}
    Xlocs = [_alpha_pow[pos] for pos in err_pos]
    A = [[gf_pow(Xlocs[c], j) for c in range(ne)] for j in range(ne)]
    rhs = syns[:ne]
    ev = solve_linear(A, rhs)
    if ev is None: return None
    corrected = received[:]
    for idx, pos in enumerate(err_pos):
        corrected[pos] ^= ev[idx]
    # Verify
    syn2 = rs_syndromes(n, k, corrected)
    if not all(s == 0 for s in syn2): return None
    return extract_message(n, k, corrected)

def extract_message(n, k, codeword):
    """Extract message from systematic codeword (last k symbols)."""
    return list(codeword[n - k:])

def solve_linear(A, b):
    m = len(A)
    if m == 0: return []
    nc = len(A[0]); aug = [A[i][:] + [b[i]] for i in range(m)]
    for col in range(min(m, nc)):
        piv = None
        for r in range(col, m):
            if aug[r][col] != 0: piv = r; break
        if piv is None: continue
        aug[col], aug[piv] = aug[piv], aug[col]
        iv = gf_inv(aug[col][col])
        for c in range(nc + 1): aug[col][c] = gf_mul(aug[col][c], iv)
        for r in range(m):
            if r == col: continue
            f = aug[r][col]
            if f:
                for c in range(nc + 1): aug[r][c] ^= gf_mul(f, aug[col][c])
    return [aug[c][nc] for c in range(min(m, nc))]

# ═══════════════════════════════════════════════════════════════════════════════
#  GS polynomial fallback
# ═══════════════════════════════════════════════════════════════════════════════

def gs_poly_fallback(n, k, received, t):
    w = k - 1
    best_m = None; best_D = None; best_L = None; best_exc = 0
    for m in range(1, 20):
        constraints = n * m * (m + 1) // 2
        if constraints > 600: break
        D = 0
        while True:
            D += 1
            nu = 0; L_test = 0
            for j in range(D // max(w, 1) + 2):
                mx = D - w * j
                if mx < 0: break
                nu += mx + 1; L_test = j
            if nu > constraints: break
            if D > 2000: break
        if D > 2000: continue
        if nu > constraints:
            if best_m is None or L_test > (best_L or 0) or (L_test == best_L and nu - constraints > best_exc):
                best_m, best_D, best_L, best_exc = m, D, L_test, nu - constraints
    if best_m is None: return []
    m_v, D, L = best_m, best_D, best_L
    mons = monomial_list(L, D, w)
    if not mons: return []
    # Points: (alpha^i, r_i)
    xs = [_alpha_pow[i] for i in range(n)]
    ys = received[:]
    rows = build_interp(xs, ys, [False] * n, m_v, mons, L)
    Ns = nullspace(rows)
    if not Ns: return []
    all_cands = []
    for vi, vec in enumerate(Ns[:10]):
        Q = vec_to_Q(vec, mons, L)
        flist = rr_series(Q, k, max_br=128)
        for f in flist:
            f = ps(f[:k])
            if pdeg(f) >= k: continue
            R = [0]; pow_f = [[1]]
            for j2 in range(1, L + 1): pow_f.append(pmul(pow_f[-1], f))
            for j2, Qj in enumerate(Q): R = padd(R, pmul(Qj, pow_f[j2]))
            if any(c != 0 for c in R): continue
            code = [peval(f, _alpha_pow[i]) for i in range(n)]
            agree = sum(1 for a2, b2 in zip(code, received) if a2 == b2)
            if agree >= n - t: all_cands.append(f)
    return dedup(k, all_cands)

# ═══════════════════════════════════════════════════════════════════════════════
#  Main decoder
# ═══════════════════════════════════════════════════════════════════════════════

def wu_decode(n, k, received, t_target=None, verbose=False):
    nsym = n - k
    syns = rs_syndromes(n, k, received)
    if all(s == 0 for s in syns):
        msg = extract_message(n, k, received)
        return [msg] if msg else []

    Lambda, B = berlekamp_massey(syns)
    L_Lam = pdeg(Lambda); L_B = pdeg(B); L_xB = L_B + 1

    # BM unique decode (works when errors <= t0)
    msg_u = _try_unique(n, k, Lambda, received, syns)

    # Early return: if BM succeeded and caller only wants unique decode, skip list decode
    if msg_u is not None and t_target is not None and t_target <= (n - k + 1) // 2:
        return [msg_u]

    par = wu_params(n, k, L_Lam, L_B, t=t_target)
    t = par['t']; t0 = par['t0']; m = par['m']; Ly = par['Ly']
    LQ = par['LQ']; w = par['w']; Ls = par['Ls']

    if not par['ok']:
        bnd = n - math.sqrt(n * (k - 1))
        t_max_abs = int(math.floor(bnd - 1e-9))
        par2 = wu_params(n, k, L_Lam, L_B, t=t_max_abs)
        if par2['ok']:
            par = par2; t = par['t']; m = par['m']; Ly = par['Ly']
            LQ = par['LQ']; w = par['w']; Ls = par['Ls']
        else:
            # Params infeasible — return BM result if available
            return [msg_u] if msg_u else []

    if L_Lam > t:
        return [msg_u] if msg_u else []
    if L_xB > t:
        return [msg_u] if msg_u else []

    # Rational points
    xs, ys, isinf = [], [], []
    for i in range(n):
        xi = _alpha_neg[i]
        lv = peval(Lambda, xi); bv = peval(B, xi)
        dn = gf_mul(xi, bv)
        xs.append(xi)
        if dn == 0:
            ys.append(0); isinf.append(True)
        else:
            ys.append(gf_div(lv, dn)); isinf.append(False)
    if verbose:
        n_inf = sum(isinf)
        print(f"    {n} rational points ({n - n_inf} finite, {n_inf} at infinity)")

    mons = monomial_list(Ly, LQ, w)
    nu = len(mons)
    max_c = n * m * (m + 1) // 2
    if max_c > 2000 or nu > 2000:
        return [msg_u] if msg_u else []

    rows = build_interp(xs, ys, isinf, m, mons, Ly)
    rows = [r for r in rows if any(v != 0 for v in r)]
    nc = len(rows)
    if verbose: print(f"    Interpolation matrix: ({nc}, {nu})")

    Ns = nullspace(rows)
    if not Ns:
        return [msg_u] if msg_u else []
    if verbose: print(f"    Nullspace dim: {len(Ns)}")

    all_cands = []
    total_series = 0
    K = Ls + 1
    for vi, vec in enumerate(Ns[:10]):
        Q = vec_to_Q(vec, mons, Ly)

        # Primary: Hensel lifting (O(log K) steps, no branching)
        slist = hensel_series(Q, K, max_roots=64)
        
        # Fallback: RR if Hensel found nothing (handles multiple roots / char 2 edge cases)
        if not slist:
            slist = rr_series(Q, K, max_br=64)

        total_series += len(slist)
        for series in slist:
            cands = recover_from_series(n, k, series, Lambda, B, L_Lam, L_xB, t, t0, received)
            all_cands.extend(cands)
        # Early exit: stop processing nullspace vectors once we have candidates
        if all_cands:
            break

    if verbose: print(f"    {total_series} power series, {len(all_cands)} candidates after recovery")

    if msg_u: all_cands.append(msg_u)

    return dedup(k, all_cands)

def _try_unique(n, k, Lambda, received, syns):
    L = pdeg(Lambda)
    if L <= 0:
        if all(s == 0 for s in syns): return extract_message(n, k, received)
        return None
    err_pos = chien_search(Lambda, n)
    if len(err_pos) != L: return None
    return decode_from_positions(n, k, err_pos, received)

def dedup(k, cands):
    seen = set(); out = []
    for f in cands:
        fp = tuple((f + [0] * k)[:k])
        if fp not in seen: seen.add(fp); out.append(list(fp))
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  QR-Compatible RS Encoding  (identical to paulmillr/qr RS.encode)
# ═══════════════════════════════════════════════════════════════════════════════

def qr_generator_poly(ecc_words):
    g = list(reversed(rs_generator(ecc_words)))
    return g

def qr_rs_encode(data_bytes, ecc_words):
    g = qr_generator_poly(ecc_words)
    pol = list(data_bytes) + [0] * ecc_words
    for i in range(len(data_bytes)):
        c = pol[i]
        if c == 0: continue
        for j in range(1, len(g)):
            if g[j]: pol[i + j] ^= gf_mul(g[j], c)
    return pol[len(data_bytes):]

def qr_rs_syndromes(codeword, ecc_words):
    syns = []
    for i in range(ecc_words):
        ai = _alpha_pow[i]; val = 0
        for c in codeword: val = gf_add(gf_mul(val, ai), c)
        syns.append(val)
    return syns

def qr_to_internal(cw): return list(reversed(cw))
def internal_msg_to_qr(msg): return list(reversed(msg))

def qr_wu_decode(cw_qr, k, ecc_words, t_target=None):
    n = len(cw_qr)
    cands = wu_decode(n, k, qr_to_internal(cw_qr), t_target=t_target, verbose=False)
    return [internal_msg_to_qr(m) for m in cands] if cands else []

# ─── Multi-block QR support ────────────────────────────────────────────────────
# Higher QR versions split data into multiple RS blocks (possibly of two
# different sizes — "group 1" and "group 2"), each encoded separately, then
# interleaved at the byte level when placed in the QR matrix.

def qr_block_layout(version, level):
    """
    Returns list of (data_bytes, ecc_bytes) tuples for each block of the
    given QR version + ECC level.

    All blocks share the same number of ECC bytes per block. Data is split
    so that "group 2" blocks (placed at the end) carry one extra data byte.
    """
    idx = version - 1
    total = QR_TOTAL[idx]
    ecc_per_block = QR_ECC_WORDS[level][idx]
    nb = QR_BLOCKS[level][idx]
    data_total = total - nb * ecc_per_block
    base = data_total // nb
    extras = data_total % nb
    blocks = []
    for _ in range(nb - extras):
        blocks.append((base, ecc_per_block))
    for _ in range(extras):
        blocks.append((base + 1, ecc_per_block))
    return blocks

def rs_decoder_bounds(data_bytes, ecc_bytes):
    """Return BM and Wu radii for one QR RS block."""
    n = data_bytes + ecc_bytes
    t0 = ecc_bytes // 2
    t_max = max(
        t0,
        int(math.floor(n - math.sqrt(n * max(data_bytes - 1, 1)) - 1e-9)),
    )
    return {
        'n': n,
        'k': data_bytes,
        'ecc': ecc_bytes,
        'd': ecc_bytes + 1,
        't0': t0,
        't_max': t_max,
        'gap': t_max - t0,
    }

def qr_block_bounds(version, level):
    """Return per-block decoder bounds for a QR version + level."""
    return [rs_decoder_bounds(data_bytes, ecc_bytes)
            for data_bytes, ecc_bytes in qr_block_layout(version, level)]

def qr_worst_block_bounds(version, level):
    """
    Return the conservative per-block bound for a QR layout.

    Mixed QR layouts have group-1 blocks with k data bytes and group-2 blocks
    with k+1 data bytes. The Wu radius depends on each block's own n and k, so
    use the minimum t_max instead of assuming blocks[0].
    """
    bounds = qr_block_bounds(version, level)
    if not bounds:
        return None
    return min(bounds, key=lambda b: (b['t_max'], b['t0'], b['n']))

def qr_block_bound_groups(version, level):
    """Return block-bound groups with counts for compact UI display."""
    groups = []
    for b in qr_block_bounds(version, level):
        for g in groups:
            if g['n'] == b['n'] and g['k'] == b['k'] and g['ecc'] == b['ecc']:
                g['count'] += 1
                break
        else:
            item = dict(b)
            item['count'] = 1
            groups.append(item)
    return groups

def qr_total_data_bytes(version, level):
    """Total user-data byte capacity (sum of all block data sizes)."""
    return sum(b[0] for b in qr_block_layout(version, level))

def qr_rs_encode_full(data, version, level):
    """
    Encode user data into a fully-interleaved QR codeword stream
    (data interleaved + ecc interleaved). The output is the byte sequence
    that gets placed in the QR matrix.
    """
    blocks = qr_block_layout(version, level)
    total_data = sum(b[0] for b in blocks)
    if len(data) < total_data:
        data = list(data) + [0] * (total_data - len(data))
    else:
        data = list(data[:total_data])

    # Split into blocks, RS-encode each
    block_data = []
    block_ecc = []
    pos = 0
    for dk, ecc in blocks:
        bd = data[pos:pos + dk]
        pos += dk
        block_data.append(bd)
        block_ecc.append(qr_rs_encode(bd, ecc))

    max_dk = max(b[0] for b in blocks)
    ecc_count = blocks[0][1]

    interleaved = []
    for i in range(max_dk):
        for bd in block_data:
            if i < len(bd):
                interleaved.append(bd[i])
    for i in range(ecc_count):
        for be in block_ecc:
            interleaved.append(be[i])
    return interleaved

def qr_de_interleave(codeword, version, level):
    """
    Reverse interleave a QR codeword stream into per-block (data, ecc) pairs.
    """
    blocks = qr_block_layout(version, level)
    nb = len(blocks)
    max_dk = max(b[0] for b in blocks)
    ecc_count = blocks[0][1]
    block_data = [[] for _ in range(nb)]
    block_ecc = [[] for _ in range(nb)]
    pos = 0
    for i in range(max_dk):
        for j in range(nb):
            if i < blocks[j][0]:
                block_data[j].append(codeword[pos])
                pos += 1
    for i in range(ecc_count):
        for j in range(nb):
            block_ecc[j].append(codeword[pos])
            pos += 1
    return list(zip(block_data, block_ecc))

def qr_interleave_blocks(block_data, block_ecc, blocks):
    """Interleave per-block (data, ecc) lists back into a single QR stream."""
    max_dk = max(b[0] for b in blocks)
    ecc_count = blocks[0][1]
    out = []
    for i in range(max_dk):
        for bd in block_data:
            if i < len(bd):
                out.append(bd[i])
    for i in range(ecc_count):
        for be in block_ecc:
            out.append(be[i])
    return out

def qr_wu_decode_full(codeword, version, level, t_target=None):
    """
    Multi-block Wu list decode. Returns a list of all mathematically valid
    concatenated user data combinations, or None on failure.
    """
    block_pairs = qr_de_interleave(codeword, version, level)
    all_block_cands = []
    
    for data_part, ecc_part in block_pairs:
        block_cw = list(data_part) + list(ecc_part)
        n = len(block_cw)
        k = len(data_part)
        ecc_w = len(ecc_part)
        
        if t_target is not None:
            cands = qr_wu_decode(block_cw, k, ecc_w, t_target=t_target)
        else:
            t0 = ecc_w // 2
            t_max_block = max(
                t0,
                int(math.floor(n - math.sqrt(n * max(k - 1, 1)) - 1e-9)),
            )
            cands = None
            for t_try in range(1, t_max_block + 1):
                cands = qr_wu_decode(block_cw, k, ecc_w, t_target=t_try)
                if cands:
                    break
                    
        if not cands:
            return None
        all_block_cands.append(cands)
        
    # Generate every combination if multiple blocks have multiple candidates
    full_cands = []
    for combination in itertools.product(*all_block_cands):
        full_data = []
        for bd in combination:
            full_data.extend(bd)
        full_cands.append(full_data)
        
    return full_cands

# ═══════════════════════════════════════════════════════════════════════════════
#  QR Code RS Parameters (from paulmillr/qr)
# ═══════════════════════════════════════════════════════════════════════════════

QR_ECC_WORDS = {
    'low':      [7,10,15,20,26,18,20,24,30,18,20,24,26,30,22,24,28,30,28,28,28,28,30,30,26,28,30,30,30,30,30,30,30,30,30,30,30,30,30,30],
    'medium':   [10,16,26,18,24,16,18,22,22,26,30,22,22,24,24,28,28,26,26,26,26,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28,28],
    'quartile': [13,22,18,26,18,24,18,22,20,24,28,26,24,20,30,24,28,28,26,30,28,30,30,30,30,28,30,30,30,30,30,30,30,30,30,30,30,30,30,30],
    'high':     [17,28,22,16,22,28,26,26,24,28,24,28,22,24,24,30,28,28,26,28,30,24,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30,30],
}
QR_TOTAL = [26,44,70,100,134,172,196,242,292,346,404,466,532,581,655,733,815,901,991,1085,1156,1258,1364,1474,1588,1706,1828,1921,2051,2185,2323,2465,2611,2761,2876,3034,3196,3362,3532,3706]
QR_BLOCKS = {
    'low':      [1,1,1,1,1,2,2,2,2,4,4,4,4,4,6,6,6,6,7,8,8,9,9,10,12,12,12,13,14,15,16,17,18,19,19,20,21,22,24,25],
    'medium':   [1,1,1,2,2,4,4,4,5,5,5,8,9,9,10,10,11,13,14,16,17,17,18,20,21,23,25,26,28,29,31,33,35,37,38,40,43,45,47,49],
    'quartile': [1,1,2,2,4,4,6,6,8,8,8,10,12,16,12,17,16,18,21,20,23,23,25,27,29,34,34,35,38,40,43,45,48,51,53,56,59,62,65,68],
    'high':     [1,1,2,4,4,4,5,6,8,8,11,11,16,16,18,16,19,21,25,25,25,34,30,32,35,37,40,42,45,48,51,54,57,60,63,66,70,74,77,81],
}

def fmt_hex(lst):
    return '[' + ', '.join(f'{x:02X}' for x in lst) + ']'

def fmt_hex_short(lst, mx=16):
    if len(lst) <= mx: return fmt_hex(lst)
    return '[' + ', '.join(f'{x:02X}' for x in lst[:mx]) + f', ... ({len(lst)} bytes)]'

def banner(text, w=70, ch='='):
    print(ch * w); print(f'  {text}'); print(ch * w)

def section(label):
    print(f"\n{'─'*70}\n  {label}\n{'─'*70}")

# ═══════════════════════════════════════════════════════════════════════════════
#  Main CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print()
    banner("WU'S LIST DECODER FOR QR-CODE REED-SOLOMON OVER GF(2^8)")
    print(f"""
  Reference : Wu, "New List Decoding Algorithms for
               Reed-Solomon and BCH Codes", ISIT 2007

  Field          : GF(2^8)  with  x^8 + x^4 + x^3 + x^2 + 1
  Prim. element  : alpha = 0x02
  RS encoding    : Systematic generator polynomial
                   g(x) = prod(x - alpha^i), identical to paulmillr/qr
  Byte order     : Big-endian [data | ecc]  (QR standard)
""")
    print("  Available QR configurations (V1-V40, single & multi-block):\n")
    configs = []
    for ver in range(1, 41):
        for level in ['low', 'medium', 'quartile', 'high']:
            idx = ver - 1
            ecc_w = QR_ECC_WORDS[level][idx]
            total = QR_TOTAL[idx]
            nb = QR_BLOCKS[level][idx]
            blocks = qr_block_layout(ver, level)
            first_bound = rs_decoder_bounds(*blocks[0])
            worst_bound = qr_worst_block_bounds(ver, level)
            bk_data, bk_ecc = first_bound['k'], first_bound['ecc']
            n_b = first_bound['n']
            t0_b = worst_bound['t0']
            t_max_b = worst_bound['t_max']
            gap_b = t_max_b - t0_b
            total_data = sum(b[0] for b in blocks)
            configs.append((ver, level, blocks, total_data, t0_b, t_max_b, gap_b))
    # Pretty-print in 2 columns to keep the menu compact
    for ci, c in enumerate(configs, start=1):
        ver, level, blocks, total_data, t0_b, t_max_b, gap_b = c
        nb = len(blocks)
        bk_data, bk_ecc = blocks[0]
        n_b = bk_data + bk_ecc
        block_str = f"{nb}x RS({n_b},{bk_data})" if nb > 1 else f"RS({n_b},{bk_data})"
        print(f"    [{ci:3d}] V{ver:2d}-{level:8s}  {block_str:14s}  "
              f"data={total_data:4d}B  BM/blk={t0_b:2d}  Wu/blk={t_max_b:2d} (+{gap_b})")
    print()
    while True:
        try:
            ch = int(input(f"  Select configuration (1-{len(configs)}): ").strip())
            if 1 <= ch <= len(configs): break
        except ValueError: pass
        except (EOFError, KeyboardInterrupt): print(); return
        print(f"    Enter 1-{len(configs)}.")

    ver, level, blocks, total_data, t0, t_max, gap = configs[ch - 1]
    nb = len(blocks)
    bk_data, ecc_w = blocks[0]
    n_b = bk_data + ecc_w
    n = n_b * nb if all(b == blocks[0] for b in blocks) else sum(b[0] + b[1] for b in blocks)
    k = total_data  # full user-data capacity
    print(f"\n  Selected: QR Version {ver}, ECC {level.upper()}")
    if nb == 1:
        print(f"  Single block: RS({n_b}, {bk_data}) over GF(2^8),  d = {ecc_w+1}")
    else:
        # Show both block sizes if mixed
        sizes = sorted({(b[0]+b[1], b[0]) for b in blocks})
        sz_strs = [f"RS({nn},{kk})" for nn, kk in sizes]
        cnt = {s: sum(1 for b in blocks if (b[0]+b[1], b[0]) == s) for s in sizes}
        layout = " + ".join(f"{cnt[s]}x{ss}" for s, ss in zip(sizes, sz_strs))
        print(f"  Multi-block: {layout}  ({nb} blocks total)")
    print(f"  Total user data  : {total_data} bytes")
    print(f"  BM unique radius : {t0} byte errors / block")
    print(f"  Wu list bound    : {t_max} byte errors / block  (+{gap} beyond BM)")

    # Multi-block QR codes get their own simplified flow.
    if nb > 1:
        _multi_block_demo(ver, level, blocks, total_data, t0, t_max)
        return

    # ── STEP 0: Encode ──
    section("STEP 0: MESSAGE INPUT & QR-STYLE RS ENCODING")

    print(f"\n  The RS({n}, {k}) code carries {k} data bytes.")
    print(f"  In a real QR code, your text is converted to bytes first")
    print(f"  (byte mode: each character -> its ASCII code),")
    print(f"  then those bytes are RS-encoded for error protection.\n")

    while True:
        try:
            raw = input(f"  Type your message (max {k} characters, or ENTER for random): ").strip()
            break
        except (EOFError, KeyboardInterrupt): print(); return

    if raw == '':
        seed = random.randrange(100000); random.seed(seed)
        data = [random.randrange(256) for _ in range(k)]
        print(f"\n  (Using random data, seed={seed})")
    else:
        # Truncate to k bytes, pad with zeros if shorter
        msg_bytes = raw.encode('utf-8')[:k]
        data = list(msg_bytes) + [0] * (k - len(msg_bytes))
        print(f"\n  Input text: \"{raw}\"")

    # Show the byte conversion
    print(f"\n  ┌─ Byte Encoding (QR Byte Mode) ──────────────────────────")
    print(f"  │")
    for i, b in enumerate(data):
        ch = chr(b) if 32 <= b < 127 else '.'
        print(f"  │  data[{i:2d}] = '{ch}'  ->  0x{b:02X}  ({b:3d})")
    print(f"  │")
    print(f"  │  Data bytes ({k}): {fmt_hex(data)}")
    print(f"  └────────────────────────────────────────────────────────")

    # RS Encoding
    print(f"\n  ┌─ RS Encoding ────────────────────────────────────────────")
    print(f"  │")
    print(f"  │  Generator polynomial:")
    print(f"  │    g(x) = (x-α^0)(x-α^1)...(x-α^{ecc_w-1})")
    g_be = qr_generator_poly(ecc_w)
    print(f"  │    g(x) = {fmt_hex_short(g_be)}  ({ecc_w+1} coefficients)")
    print(f"  │")
    print(f"  │  Encoding steps (identical to paulmillr/qr):")
    print(f"  │    1. Treat data as polynomial:  d(x) = d[0]*x^{n-1} + d[1]*x^{n-2} + ... + d[{k-1}]*x^{ecc_w}")
    print(f"  │    2. Divide d(x) by g(x):       d(x) = q(x)*g(x) + r(x)")
    print(f"  │    3. Parity = remainder r(x):    {ecc_w} bytes")
    print(f"  │    4. Codeword = data + parity:   {k} + {ecc_w} = {n} bytes")

    ecc = qr_rs_encode(data, ecc_w)
    cw = data + ecc

    print(f"  │")
    print(f"  │  Result:")
    print(f"  │    Data   ({k:2d} bytes): {fmt_hex(data)}")
    print(f"  │    Parity ({ecc_w:2d} bytes): {fmt_hex(ecc)}")
    print(f"  │")
    print(f"  │    Codeword [{k} data | {ecc_w} ECC] = {n} bytes:")
    print(f"  │    {fmt_hex_short(cw)}")
    print(f"  │")
    assert all(s == 0 for s in qr_rs_syndromes(cw, ecc_w))
    print(f"  │  Verification: R(α^i) = 0 for i=0..{ecc_w-1}  [PASS]")
    print(f"  └────────────────────────────────────────────────────────")

    # ── STEP 1: Errors ──
    section("STEP 1: CHANNEL NOISE INJECTION")
    print(f"\n  How many byte errors?")
    print(f"    [1-{t0}]    BM unique decoding")
    if gap > 0: print(f"    [{t0+1}-{t_max}]   Wu list decoding  (+{gap} beyond BM)")
    print(f"    [{t_max+1}+]     Beyond guaranteed correction\n")
    while True:
        try:
            te = int(input(f"  Enter number of errors (1-{n}): ").strip())
            if 1 <= te <= n: break
        except ValueError: pass
        except (EOFError, KeyboardInterrupt): print(); return
        print(f"    Enter 1-{n}.")

    ep = sorted(random.sample(range(n), te))
    rec = cw[:]; emag = []
    for i in ep:
        d2 = random.randrange(1, 256); emag.append(d2); rec[i] ^= d2
    de = [p for p in ep if p < k]; ee = [p for p in ep if p >= k]
    ag = sum(1 for a, b in zip(cw, rec) if a == b)

    print(f"\n  Errors injected   : {te}")
    print(f"  Error positions   : {ep}")
    print(f"    Data region     : {de} ({len(de)} of {k})")
    print(f"    ECC region      : {ee} ({len(ee)} of {ecc_w})")
    print(f"  Error magnitudes  : {fmt_hex(emag)}")
    print(f"  Received ({n:2d})    : {fmt_hex_short(rec)}")
    print(f"  Agreement         : {ag}/{n}")

    if te <= t0: lbl = f"Within BM radius (t0={t0})"
    elif te <= t_max: lbl = f"Beyond BM, within Wu bound (t0={t0} < {te} <= t_max={t_max})"
    else: lbl = f"Beyond guaranteed correction (t_max={t_max})"
    print(f"\n  {te} errors : {lbl}")

    # ── STEP 2: Syndromes ──
    section("STEP 2: SYNDROME CALCULATION")
    syns = qr_rs_syndromes(rec, ecc_w)
    print(f"\n  S_i = R(alpha^i) for i = 0..{ecc_w-1}")
    print(f"  Syndromes: {fmt_hex(syns)}")

    # ── STEP 3: BM ──
    section("STEP 3: BERLEKAMP-MASSEY ALGORITHM")
    cw_int = qr_to_internal(rec)
    syns_int = rs_syndromes(n, k, cw_int)
    Lam, B = berlekamp_massey(syns_int)
    print(f"\n  Lambda(x) degree : {pdeg(Lam)}")
    print(f"  B(x) degree      : {pdeg(B)}")
    print(f"  L_Lambda + L_B   : {pdeg(Lam)+pdeg(B)}  (== n-k = {ecc_w})")

    # ── STEP 4: Decode ──
    if te <= t0:
        section("STEP 4: UNIQUE DECODING (BM + Chien + Forney)")
        print(f"\n  {te} errors <= t0={t0}: direct BM decode...")
        cands = qr_wu_decode(rec, k, ecc_w, t_target=te)
        if cands:
            md = cands[0]; m_ok = md == data
            print(f"\n  Decoded data (hex): {fmt_hex(md)}")
            txt = _try_text(md)
            if txt: print(f"  Decoded text     : \"{txt}\"")
            section("RESULT")
            if m_ok:
                print(f"\n  EXACT MATCH with original data!")
                print(f"  Unique decoding: {te} byte error(s) corrected.")
            else:
                print(f"\n  MISMATCH.")
        else:
            print(f"\n  BM unique decode failed. Trying Wu's list decoder...")
            _show_list(rec, data, k, ecc_w, te, t0, t_max, n, ep)
    else:
        section("STEP 4: WU'S RATIONAL LIST DECODING")
        _show_list(rec, data, k, ecc_w, te, t0, t_max, n, ep)


def _try_text(data_bytes):
    """Try to decode bytes as UTF-8 text, stripping trailing nulls."""
    stripped = data_bytes[:]
    while stripped and stripped[-1] == 0: stripped.pop()
    if not stripped: return None
    try:
        txt = bytes(stripped).decode('utf-8')
        if all(32 <= b < 127 or b in (10, 13) for b in stripped):
            return txt
    except: pass
    return None

def _show_list(rec, data_true, k, ecc_w, te, t0, t_max, n, ep):
    tt = min(te, t_max)
    print(f"\n  Running Wu's decoder with t = {tt}...")
    cands = qr_wu_decode(rec, k, ecc_w, t_target=tt)
    section("DECODING RESULTS")
    print(f"\n  List size: {len(cands)} candidate(s)")
    if not cands:
        print(f"\n  No codewords found within distance {tt}.")
        if te > t_max: print(f"  ({te} errors > t_max = {t_max})")
        print("  " + "=" * 60); return
    ft = False
    for idx, md in enumerate(cands):
        ok = md == data_true
        if ok: ft = True
        ecc_d = qr_rs_encode(md, ecc_w)
        cw_d = md + ecc_d
        errs = sorted([i for i in range(n) if cw_d[i] != rec[i]])
        print(f"\n  ┌─ Candidate {idx+1} of {len(cands)} ─────────────────────────────────")
        print(f"  │  Data (hex) : {fmt_hex(md)}")
        txt = _try_text(md)
        if txt: print(f"  │  As text    : \"{txt}\"")
        print(f"  │  Error locs : {errs}  ({len(errs)} errors)")
        if ok:
            print(f"  │")
            print(f"  │  >>> EXACT MATCH with original data! <<<")
            print(f"  │  True error positions: {ep}")
        else:
            print(f"  │  ALIAS — different valid codeword within distance {len(errs)}")
        print(f"  └──────────────────────────────────────────────────────")
    print()
    print("  " + "=" * 60)
    if ft:
        if len(cands) == 1: print(f"  DECODING SUCCESSFUL (unique answer)")
        else:
            ti = next(i+1 for i, m in enumerate(cands) if m == data_true)
            print(f"  DECODING SUCCESSFUL — Candidate {ti} of {len(cands)}")
    else:
        print(f"  DECODING FAILED — original not in list.")
        if te > t_max: print(f"  ({te} errors > t_max = {t_max})")
    print("  " + "=" * 60)


def _multi_block_demo(ver, level, blocks, total_data, t0, t_max):
    """Multi-block QR demo: encode → corrupt → de-interleave → per-block Wu."""
    nb = len(blocks)
    bk_data, ecc_w = blocks[0]
    n_block = bk_data + ecc_w
    block_bounds = qr_block_bounds(ver, level)
    bound_groups = qr_block_bound_groups(ver, level)

    # Total interleaved length
    n_total = sum(b[0] + b[1] for b in blocks)

    section("STEP 0: MESSAGE INPUT & MULTI-BLOCK RS ENCODING")
    print(f"\n  This QR version splits data into {nb} RS blocks.")
    print(f"  Each block carries ~{bk_data} data bytes + {ecc_w} ECC bytes")
    print(f"  ({total_data} total user bytes, {n_total} bytes in stream).\n")

    while True:
        try:
            raw = input(
                f"  Type your message (max {total_data} chars, ENTER for random): "
            ).strip()
            break
        except (EOFError, KeyboardInterrupt):
            print(); return

    if raw == '':
        seed = random.randrange(100000); random.seed(seed)
        data = [random.randrange(256) for _ in range(total_data)]
        print(f"\n  (Using random data, seed={seed})")
    else:
        msg_bytes = raw.encode('utf-8')[:total_data]
        data = list(msg_bytes) + [0] * (total_data - len(msg_bytes))
        print(f"\n  Input text: \"{raw}\"")

    cw = qr_rs_encode_full(data, ver, level)
    print(f"\n  Encoded {n_total}-byte interleaved stream:")
    print(f"    {fmt_hex_short(cw, mx=24)}")
    # Sanity: round-trip
    block_pairs = qr_de_interleave(cw, ver, level)
    rt = []
    for bd, _ in block_pairs:
        rt.extend(bd)
    assert rt == data, "Round-trip via de-interleave failed!"
    print(f"  Round-trip via de-interleave: OK")

    # Per-block Wu radius
    print(f"  Conservative per-block correction: BM <= {t0}, Wu <= {t_max} byte errors")
    for g in bound_groups:
        print(f"    {g['count']}x RS({g['n']},{g['k']}): BM <= {g['t0']}, Wu <= {g['t_max']}")

    section("STEP 1: CHANNEL NOISE INJECTION")
    print(f"\n  How many byte errors to inject in the {n_total}-byte stream?")
    print(f"  Note: errors are corrected per-block, so worst-case adversarial")
    print(f"  placement piles them into one block. Random spread is easier.\n")
    while True:
        try:
            te = int(input(f"  Enter number of errors (1-{n_total}): ").strip())
            if 1 <= te <= n_total: break
        except ValueError: pass
        except (EOFError, KeyboardInterrupt): print(); return

    ep = sorted(random.sample(range(n_total), te))
    rec = cw[:]
    for i in ep:
        rec[i] ^= random.randrange(1, 256)

    # Count errors per block
    block_pairs_corrupt = qr_de_interleave(rec, ver, level)
    block_pairs_orig = qr_de_interleave(cw, ver, level)
    per_block_err = []
    for (bd_o, be_o), (bd_c, be_c) in zip(block_pairs_orig, block_pairs_corrupt):
        ne = sum(1 for a, b in zip(bd_o + be_o, bd_c + be_c) if a != b)
        per_block_err.append(ne)
    print(f"\n  Errors injected: {te} total")
    print(f"  Per-block errors: {per_block_err}")
    worst = max(per_block_err)
    bm_status = all(ne <= b['t0'] for ne, b in zip(per_block_err, block_bounds))
    wu_status = all(ne <= b['t_max'] for ne, b in zip(per_block_err, block_bounds))
    print(f"  Worst block: {worst} errors  "
          f"({'within BM' if bm_status else ('within Wu' if wu_status else 'BEYOND Wu')})")

    section("STEP 2: PER-BLOCK BERLEKAMP-MASSEY + WU LIST DECODE")
    print()
    decoded_data = []
    all_ok = True
    for bi, ((bd_o, be_o), (bd_c, be_c), ne, block_bound) in enumerate(
            zip(block_pairs_orig, block_pairs_corrupt, per_block_err, block_bounds)):
        block_cw = list(bd_c) + list(be_c)
        n_b = len(block_cw); k_b = len(bd_c); ec_b = len(be_c)
        cands = qr_wu_decode(block_cw, k_b, ec_b, t_target=min(ne, block_bound['t_max']) or None)
        ok = bool(cands and cands[0] == list(bd_o))
        all_ok = all_ok and ok
        status = "OK " if ok else "FAIL"
        print(f"  Block {bi+1:2d}/{nb}  RS({n_b},{k_b})  errs={ne:2d}  "
              f"cands={len(cands) if cands else 0}  {status}")
        if cands:
            decoded_data.extend(cands[0])
        else:
            decoded_data.extend(bd_c)  # placeholder

    section("RESULT")
    print()
    if all_ok and decoded_data == data:
        print(f"  EXACT MATCH — all {nb} blocks recovered.")
        txt = _try_text(decoded_data)
        if txt: print(f"  Decoded text: \"{txt}\"")
    else:
        diff = sum(1 for a, b in zip(decoded_data, data) if a != b)
        print(f"  DECODING FAILED — {diff} byte(s) differ from original.")
    print()


if __name__ == "__main__":
    main()
