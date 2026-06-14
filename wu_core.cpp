/*
 * wu_core.cpp — C++ backend for hot-path GF(2^8) / RS / Wu list-decoder ops.
 *
 * Compiled as a pybind11 extension module.  Python fallback lives in wu_qr.py
 * and is used transparently when this module is not available.
 *
 * Build:  pip install .          (or: python setup.py build_ext --inplace)
 */

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>
#include <cmath>
#include <tuple>
#include <set>

namespace py = pybind11;

// ═══════════════════════════════════════════════════════════════════════
//  GF(2^8)  —  primitive poly 0x11D, generator α = 2
// ═══════════════════════════════════════════════════════════════════════

static uint8_t EXP[512];
static uint8_t LOG_T[256];          // LOG_T to avoid macro collisions
static uint8_t ALPHA_POW[256];
static uint8_t ALPHA_NEG[256];
static bool gf_ready = false;

static void gf_init() {
    if (gf_ready) return;
    int x = 1;
    for (int i = 0; i < 255; i++) {
        EXP[i] = (uint8_t)x;
        LOG_T[x]  = (uint8_t)i;
        x <<= 1;
        if (x & 256) x ^= 0x11D;
    }
    for (int i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
    LOG_T[0] = 0;

    ALPHA_POW[0] = 1;
    for (int i = 1; i < 256; i++) ALPHA_POW[i] = EXP[i % 255];

    ALPHA_NEG[0] = 1;
    for (int i = 1; i < 256; i++) ALPHA_NEG[i] = EXP[(255 - i) % 255];

    gf_ready = true;
}

inline uint8_t gf_mul(uint8_t a, uint8_t b) {
    if (a == 0 || b == 0) return 0;
    return EXP[LOG_T[a] + LOG_T[b]];
}
inline uint8_t gf_div(uint8_t a, uint8_t b) {
    if (a == 0) return 0;
    return EXP[(LOG_T[a] - LOG_T[b] + 255) % 255];
}
inline uint8_t gf_inv(uint8_t a) {
    return EXP[255 - LOG_T[a]];
}
inline uint8_t gf_pow(uint8_t a, int n) {
    if (n == 0) return 1;
    if (a == 0) return 0;
    return EXP[(LOG_T[a] * (n % 255) % 255 + 255) % 255];
}

// ═══════════════════════════════════════════════════════════════════════
//  Polynomial helpers  (coefficient list, index 0 = constant term)
// ═══════════════════════════════════════════════════════════════════════

using Poly = std::vector<int>;

static Poly ps(Poly c) {
    while (c.size() > 1 && c.back() == 0) c.pop_back();
    if (c.empty()) c.push_back(0);
    return c;
}

static int pdeg(const Poly& c) {
    Poly t = ps(Poly(c));
    if (t.size() == 1 && t[0] == 0) return -1;
    return (int)t.size() - 1;
}

static Poly padd(const Poly& a, const Poly& b) {
    size_t n = std::max(a.size(), b.size());
    Poly out(n, 0);
    for (size_t i = 0; i < a.size(); i++) out[i] ^= a[i];
    for (size_t i = 0; i < b.size(); i++) out[i] ^= b[i];
    return ps(out);
}

static Poly pmul(const Poly& a, const Poly& b) {
    if ((a.size() == 1 && a[0] == 0) || (b.size() == 1 && b[0] == 0))
        return {0};
    Poly out(a.size() + b.size() - 1, 0);
    for (size_t i = 0; i < a.size(); i++) {
        if (a[i] == 0) continue;
        int la = LOG_T[a[i]];
        for (size_t j = 0; j < b.size(); j++) {
            if (b[j] == 0) continue;
            out[i + j] ^= EXP[la + LOG_T[b[j]]];
        }
    }
    return ps(out);
}

static Poly pscalar(const Poly& a, int c) {
    if (c == 0) return {0};
    Poly out(a.size());
    for (size_t i = 0; i < a.size(); i++) out[i] = gf_mul((uint8_t)a[i], (uint8_t)c);
    return ps(out);
}

static int peval(const Poly& a, int x) {
    int acc = 0;
    for (int i = (int)a.size() - 1; i >= 0; i--)
        acc = gf_mul((uint8_t)acc, (uint8_t)x) ^ a[i];
    return acc;
}

static Poly pmod(Poly a, const Poly& m) {
    a = ps(a);
    Poly mm = ps(Poly(m));
    int il = gf_inv((uint8_t)mm.back());
    while (a.size() >= mm.size() && !(a.size() == 1 && a[0] == 0)) {
        int c = gf_mul((uint8_t)a.back(), (uint8_t)il);
        int s = (int)a.size() - (int)mm.size();
        for (size_t k = 0; k < mm.size(); k++)
            a[s + k] ^= gf_mul((uint8_t)mm[k], (uint8_t)c);
        a = ps(a);
    }
    return a;
}

static Poly pgcd(Poly a, Poly b) {
    a = ps(a); b = ps(b);
    while (!(b.size() == 1 && b[0] == 0)) {
        Poly t = pmod(a, b);
        a = b; b = t;
    }
    if (!(a.size() == 1 && a[0] == 0))
        a = pscalar(a, gf_inv((uint8_t)a.back()));
    return a;
}

// ═══════════════════════════════════════════════════════════════════════
//  Truncated polynomial ops (mod x^m)
// ═══════════════════════════════════════════════════════════════════════

static Poly ptrunc(const Poly& a, int m) {
    if (m <= 0) return {0};
    Poly out(m, 0);
    for (int i = 0; i < m && i < (int)a.size(); i++) out[i] = a[i];
    return ps(out);
}

static Poly pmul_mod(const Poly& a, const Poly& b, int m) {
    if ((a.size() == 1 && a[0] == 0) || (b.size() == 1 && b[0] == 0))
        return {0};
    Poly out(m, 0);
    for (size_t i = 0; i < a.size() && (int)i < m; i++) {
        if (a[i] == 0) continue;
        int la = LOG_T[a[i]];
        int jmax = std::min((int)b.size(), m - (int)i);
        for (int j = 0; j < jmax; j++) {
            if (b[j] == 0) continue;
            out[i + j] ^= EXP[la + LOG_T[b[j]]];
        }
    }
    return ps(out);
}

static Poly pinv_mod(const Poly& f, int m) {
    if (f.empty() || f[0] == 0) return {};   // not invertible
    Poly g = {(int)gf_inv((uint8_t)f[0])};
    int prec = 1;
    while (prec < m) {
        int np = std::min(prec * 2, m);
        Poly g2 = pmul_mod(g, g, np);
        g = pmul_mod(f, g2, np);
        prec = np;
    }
    return ptrunc(g, m);
}

// ═══════════════════════════════════════════════════════════════════════
//  RS encode / syndromes
// ═══════════════════════════════════════════════════════════════════════

static std::vector<Poly> gen_cache;
static std::vector<int>  gen_cache_nsym;

static Poly rs_generator(int nsym) {
    for (size_t i = 0; i < gen_cache_nsym.size(); i++)
        if (gen_cache_nsym[i] == nsym) return gen_cache[i];
    Poly g = {1};
    for (int i = 0; i < nsym; i++)
        g = pmul(g, {(int)ALPHA_POW[i], 1});
    gen_cache_nsym.push_back(nsym);
    gen_cache.push_back(g);
    return g;
}

static std::vector<int> rs_syndromes(int n, int k, const std::vector<int>& received) {
    int nsym = n - k;
    std::vector<int> syns(nsym);
    for (int j = 0; j < nsym; j++) {
        Poly r(received.begin(), received.end());
        syns[j] = peval(r, (int)ALPHA_POW[j]);
    }
    return syns;
}

// ═══════════════════════════════════════════════════════════════════════
//  Berlekamp-Massey
// ═══════════════════════════════════════════════════════════════════════

static std::pair<Poly, Poly> berlekamp_massey(const std::vector<int>& S) {
    int N = (int)S.size();
    Poly C = {1}, B = {1};
    int L = 0, dp = 1;

    for (int r = 0; r < N; r++) {
        int delta = S[r];
        for (int i = 1; i <= L; i++) {
            if (i < (int)C.size() && r - i >= 0)
                delta ^= gf_mul((uint8_t)C[i], (uint8_t)S[r - i]);
        }
        Poly T = C;
        if (delta != 0) {
            int sc = gf_mul((uint8_t)delta, gf_inv((uint8_t)dp));
            Poly xB(B.size() + 1, 0);
            for (size_t i = 0; i < B.size(); i++) xB[i + 1] = B[i];
            Poly xBs(xB.size());
            for (size_t i = 0; i < xB.size(); i++)
                xBs[i] = gf_mul((uint8_t)xB[i], (uint8_t)sc);
            size_t ml = std::max(C.size(), xBs.size());
            Poly newC(ml, 0);
            for (size_t i = 0; i < C.size(); i++) newC[i] ^= C[i];
            for (size_t i = 0; i < xBs.size(); i++) newC[i] ^= xBs[i];
            C = ps(newC);
            if (2 * L <= r) {
                B = T; L = r + 1 - L; dp = delta;
            } else {
                Poly newB(B.size() + 1, 0);
                for (size_t i = 0; i < B.size(); i++) newB[i + 1] = B[i];
                B = newB;
            }
        } else {
            Poly newB(B.size() + 1, 0);
            for (size_t i = 0; i < B.size(); i++) newB[i + 1] = B[i];
            B = newB;
        }
    }
    C = ps(C); B = ps(B);
    if (C[0] != 0) {
        int iv = gf_inv((uint8_t)C[0]);
        for (auto& c : C) c = gf_mul((uint8_t)c, (uint8_t)iv);
    }
    return {ps(C), ps(B)};
}

// ═══════════════════════════════════════════════════════════════════════
//  Nullspace via Gaussian elimination over GF(2^8)
// ═══════════════════════════════════════════════════════════════════════

static std::vector<std::vector<int>> nullspace(std::vector<std::vector<int>>& A) {
    int m = (int)A.size();
    if (m == 0) return {};
    int nc = (int)A[0].size();

    // Flatten to contiguous buffer for cache friendliness
    std::vector<uint8_t> M(m * nc);
    for (int r = 0; r < m; r++)
        for (int c = 0; c < nc; c++)
            M[r * nc + c] = (uint8_t)A[r][c];

    int row = 0;
    std::vector<int> pivs;

    for (int col = 0; col < nc && row < m; col++) {
        // Find pivot
        int piv = -1;
        for (int r = row; r < m; r++) {
            if (M[r * nc + col] != 0) { piv = r; break; }
        }
        if (piv < 0) continue;

        // Swap rows
        if (piv != row) {
            for (int j = 0; j < nc; j++)
                std::swap(M[row * nc + j], M[piv * nc + j]);
        }

        // Scale pivot row
        uint8_t iv = gf_inv(M[row * nc + col]);
        for (int j = 0; j < nc; j++)
            M[row * nc + j] = gf_mul(M[row * nc + j], iv);

        // Eliminate other rows
        for (int r = 0; r < m; r++) {
            if (r == row) continue;
            uint8_t f = M[r * nc + col];
            if (f == 0) continue;
            int lf = LOG_T[f];
            for (int j = 0; j < nc; j++) {
                if (M[row * nc + j] == 0) continue;
                M[r * nc + j] ^= EXP[lf + LOG_T[M[row * nc + j]]];
            }
        }
        pivs.push_back(col);
        row++;
    }

    // Extract free columns
    std::set<int> piv_set(pivs.begin(), pivs.end());
    std::vector<int> free_cols;
    for (int c = 0; c < nc; c++)
        if (piv_set.find(c) == piv_set.end()) free_cols.push_back(c);

    if (free_cols.empty()) return {};

    std::vector<std::vector<int>> basis;
    for (int fc : free_cols) {
        std::vector<int> v(nc, 0);
        v[fc] = 1;
        for (int idx = 0; idx < (int)pivs.size(); idx++)
            v[pivs[idx]] = (int)M[idx * nc + fc];
        basis.push_back(v);
    }
    return basis;
}

// ═══════════════════════════════════════════════════════════════════════
//  Interpolation matrix  (the #1 bottleneck)
// ═══════════════════════════════════════════════════════════════════════

static int binom2(int n, int k) {
    if (k < 0 || k > n) return 0;
    return ((k & n) == k) ? 1 : 0;
}

static std::vector<std::pair<int,int>> monomial_list(int Ly, int LQ, int w) {
    std::vector<std::pair<int,int>> mons;
    for (int j = 0; j <= Ly; j++) {
        int mx = LQ - w * j;
        if (mx < 0) continue;
        for (int i = 0; i <= mx; i++)
            mons.push_back({i, j});
    }
    return mons;
}

static std::vector<std::vector<int>> build_interp(
    const std::vector<int>& xs,
    const std::vector<int>& ys,
    const std::vector<bool>& is_inf,
    int m_val,
    const std::vector<std::pair<int,int>>& mons,
    int Ly)
{
    int nm = (int)mons.size();
    if (nm == 0) return {};

    int mi = 0, mj = 0;
    for (auto& [i, j] : mons) { mi = std::max(mi, i); mj = std::max(mj, j); }

    // Extract monomial indices
    std::vector<int> mon_i(nm), mon_j(nm);
    for (int k = 0; k < nm; k++) { mon_i[k] = mons[k].first; mon_j[k] = mons[k].second; }

    // Precompute binom2 masks for finite and infinite points
    // fin_masks[(a,b)] = list of monomial indices where mask is true
    // Using flat indexing: key = a * m_val + b
    std::vector<std::vector<int>> fin_masks(m_val * m_val);
    for (int a = 0; a < m_val; a++) {
        for (int b = 0; b < m_val - a; b++) {
            auto& mask = fin_masks[a * m_val + b];
            for (int k = 0; k < nm; k++) {
                int i = mon_i[k], j = mon_j[k];
                if (i >= a && j >= b && (a & i) == a && (b & j) == b)
                    mask.push_back(k);
            }
        }
    }
    std::vector<std::vector<int>> inf_masks(m_val * m_val);
    for (int a = 0; a < m_val; a++) {
        for (int b = 0; b < m_val - a; b++) {
            if (b > Ly) continue;
            int jt = Ly - b;
            auto& mask = inf_masks[a * m_val + b];
            for (int k = 0; k < nm; k++) {
                int i = mon_i[k], j = mon_j[k];
                if (j == jt && i >= a && (a & i) == a)
                    mask.push_back(k);
            }
        }
    }

    std::vector<std::vector<int>> rows;
    rows.reserve(xs.size() * m_val * (m_val + 1) / 2);

    // Pre-allocate power tables
    std::vector<uint8_t> px(mi + 1), py(mj + 1);
    std::vector<int> row_buf(nm);

    for (int ti = 0; ti < (int)xs.size(); ti++) {
        uint8_t xt = (uint8_t)xs[ti];

        if (!is_inf[ti]) {
            uint8_t yt = (uint8_t)ys[ti];

            // Compute power tables
            px[0] = 1;
            for (int e = 1; e <= mi; e++) px[e] = gf_mul(px[e-1], xt);
            py[0] = 1;
            for (int e = 1; e <= mj; e++) py[e] = gf_mul(py[e-1], yt);

            for (int a = 0; a < m_val; a++) {
                for (int b = 0; b < m_val - a; b++) {
                    const auto& mask = fin_masks[a * m_val + b];
                    std::memset(row_buf.data(), 0, nm * sizeof(int));
                    for (int idx : mask) {
                        uint8_t pxv = px[mon_i[idx] - a];
                        uint8_t pyv = py[mon_j[idx] - b];
                        row_buf[idx] = gf_mul(pxv, pyv);
                    }
                    rows.push_back(std::vector<int>(row_buf.begin(), row_buf.end()));
                }
            }
        } else {
            px[0] = 1;
            for (int e = 1; e <= mi; e++) px[e] = gf_mul(px[e-1], xt);

            for (int a = 0; a < m_val; a++) {
                for (int b = 0; b < m_val - a; b++) {
                    if (b > Ly) continue;
                    const auto& mask = inf_masks[a * m_val + b];
                    std::memset(row_buf.data(), 0, nm * sizeof(int));
                    for (int idx : mask) {
                        row_buf[idx] = (int)px[mon_i[idx] - a];
                    }
                    rows.push_back(std::vector<int>(row_buf.begin(), row_buf.end()));
                }
            }
        }
    }
    return rows;
}

// ═══════════════════════════════════════════════════════════════════════
//  Chien search
// ═══════════════════════════════════════════════════════════════════════

static std::vector<int> chien_search(const Poly& poly, int n) {
    int deg = pdeg(poly);
    if (deg <= 0) return {};

    std::vector<uint8_t> regs(deg + 1, 0);
    std::vector<uint8_t> mults(deg + 1);
    for (int j = 0; j <= deg; j++) {
        regs[j] = (j < (int)poly.size()) ? (uint8_t)poly[j] : 0;
        mults[j] = ALPHA_NEG[j];
    }

    std::vector<int> err_pos;
    for (int i = 0; i < n; i++) {
        uint8_t val = 0;
        for (int j = 0; j <= deg; j++) val ^= regs[j];
        if (val == 0) err_pos.push_back(i);
        for (int j = 0; j <= deg; j++)
            regs[j] = gf_mul(regs[j], mults[j]);
    }
    return err_pos;
}

// ═══════════════════════════════════════════════════════════════════════
//  Hensel lifting
// ═══════════════════════════════════════════════════════════════════════

using QPoly = std::vector<Poly>;  // Q[j] = coefficient of y^j

static Poly Q_eval_series(const QPoly& Q, const Poly& s, int m) {
    Poly result = ptrunc(Q[0], m);
    Poly s_pow = {1};
    for (int j = 1; j < (int)Q.size(); j++) {
        s_pow = pmul_mod(s_pow, s, m);
        if (!(Q[j].size() == 1 && Q[j][0] == 0)) {
            Poly term = pmul_mod(Q[j], s_pow, m);
            result = padd(result, term);
        }
    }
    return ptrunc(result, m);
}

static Poly Qy_eval_series(const QPoly& Q, const Poly& s, int m) {
    Poly result = {0};
    Poly s_pow = {1};
    for (int j = 1; j < (int)Q.size(); j++) {
        if (j % 2 == 1) {
            if (!(Q[j].size() == 1 && Q[j][0] == 0)) {
                Poly term = pmul_mod(Q[j], s_pow, m);
                result = padd(result, term);
            }
        }
        s_pow = pmul_mod(s_pow, s, m);
    }
    return ptrunc(result, m);
}

static bool poly_is_zero(const Poly& p) {
    for (int c : p) if (c != 0) return false;
    return true;
}

static std::vector<Poly> hensel_series(const QPoly& Q, int K, int max_roots = 64) {
    int Ly = (int)Q.size() - 1;
    if (Ly < 0) return {};

    // Step 1: find roots at x=0
    std::vector<int> P0(Ly + 1, 0);
    for (int j = 0; j <= Ly; j++)
        P0[j] = (Q[j].size() > 0 && Q[j][0] != 0) ? Q[j][0] : 0;

    std::vector<int> initial_roots;
    for (int y = 0; y < 256; y++) {
        int val = 0, py = 1;
        for (int j = 0; j <= Ly; j++) {
            val ^= gf_mul((uint8_t)P0[j], (uint8_t)py);
            py = gf_mul((uint8_t)py, (uint8_t)y);
        }
        if (val == 0) initial_roots.push_back(y);
    }
    if ((int)initial_roots.size() > max_roots)
        initial_roots.resize(max_roots);

    std::vector<Poly> results;
    for (int y0 : initial_roots) {
        Poly s = {y0};
        int prec = 1;
        bool success = true;

        while (prec < K) {
            int new_prec = std::min(prec * 2, K);
            Poly Qs = Q_eval_series(Q, s, new_prec);

            if (poly_is_zero(ptrunc(Qs, new_prec))) {
                s.resize(new_prec, 0);
                prec = new_prec;
                continue;
            }

            Poly Qys = Qy_eval_series(Q, s, new_prec);
            if (poly_is_zero(Qys) || Qys[0] == 0) {
                success = false;
                break;
            }

            Poly Qys_inv = pinv_mod(Qys, new_prec);
            if (Qys_inv.empty()) { success = false; break; }

            Poly delta = pmul_mod(Qs, Qys_inv, new_prec);
            Poly s_pad(new_prec, 0);
            for (int i = 0; i < (int)s.size() && i < new_prec; i++) s_pad[i] = s[i];
            Poly dt = ptrunc(delta, new_prec);
            s = ptrunc(padd(s_pad, dt), new_prec);
            prec = new_prec;
        }

        s.resize(K, 0);
        Poly Qs_final = Q_eval_series(Q, s, K);
        if (poly_is_zero(ptrunc(Qs_final, K)))
            results.push_back(s);
    }

    // Dedup
    std::set<std::vector<int>> seen;
    std::vector<Poly> uniq;
    for (auto& s : results) {
        if (seen.insert(s).second)
            uniq.push_back(s);
    }
    return uniq;
}

// ═══════════════════════════════════════════════════════════════════════
//  RR series – linear-probing Roth-Ruckenstein (stack-based DFS)
//  (reuses Q_eval_series from Hensel section above)
// ═══════════════════════════════════════════════════════════════════════

// Forward declaration
static QPoly Qshift(const QPoly& Q, int c);

static std::vector<Poly> rr_series(const QPoly& Q, int K, int max_br = 256) {
    int Ly = (int)Q.size() - 1;
    if (Ly < 0) return {};

    // DFS stack: each frame carries the shifted polynomial
    struct Frame { QPoly Q; Poly pre; int dep; };
    std::vector<Frame> stack;
    stack.push_back({Q, {}, 0});
    std::vector<Poly> results;

    while (!stack.empty() && (int)results.size() < max_br) {
        Frame f = std::move(stack.back()); stack.pop_back();
        if (f.dep >= K) {
            f.pre.resize(K);
            results.push_back(f.pre);
            continue;
        }

        // Extract P(y) = Q(0, y) from the shifted polynomial
        std::vector<int> P0(f.Q.size(), 0);
        for (int j = 0; j < (int)f.Q.size(); j++)
            P0[j] = (f.Q[j].size() > 0) ? f.Q[j][0] : 0;

        // Linear probing: evaluate P(0) and P(1)
        int C0 = P0.empty() ? 0 : P0[0];  // P(0)
        int C1 = 0;
        for (int c : P0) C1 ^= c;  // P(1) = sum of coefficients in char 2
        int A = C1 ^ C0;  // slope

        if (A != 0 && (int)P0.size() <= 2) {
            // Linear in y: unique root c = C0/A
            int ct = gf_div((uint8_t)C0, (uint8_t)A);
            Poly np2 = f.pre; np2.push_back(ct);
            if (f.dep + 1 >= K) {
                np2.resize(K); results.push_back(np2);
            } else {
                QPoly Qn = Qshift(f.Q, ct);
                if (Qn.empty()) { np2.resize(K, 0); results.push_back(np2); }
                else stack.push_back({std::move(Qn), std::move(np2), f.dep + 1});
            }
        } else {
            // Full root search over GF(256) for the shifted P(y)
            bool allzero = true;
            for (int c : P0) if (c != 0) { allzero = false; break; }

            if (allzero) {
                // Zero polynomial: any c_t works -> branch all 256
                for (int ct = 0; ct < 256 && (int)results.size() < max_br; ct++) {
                    Poly np2 = f.pre; np2.push_back(ct);
                    if (f.dep + 1 >= K) { np2.resize(K); results.push_back(np2); continue; }
                    QPoly Qn = Qshift(f.Q, ct);
                    if (Qn.empty()) { np2.resize(K, 0); results.push_back(np2); continue; }
                    stack.push_back({std::move(Qn), std::move(np2), f.dep + 1});
                }
            } else {
                // Find roots of P(y) by brute force
                std::vector<int> roots;
                for (int y = 0; y < 256; y++) {
                    int val = 0, py = 1;
                    for (int j = 0; j < (int)P0.size(); j++) {
                        val ^= gf_mul((uint8_t)P0[j], (uint8_t)py);
                        py = gf_mul((uint8_t)py, (uint8_t)y);
                    }
                    if (val == 0) roots.push_back(y);
                }
                for (int ct : roots) {
                    if ((int)results.size() >= max_br) break;
                    Poly np2 = f.pre; np2.push_back(ct);
                    if (f.dep + 1 >= K) { np2.resize(K); results.push_back(np2); continue; }
                    QPoly Qn = Qshift(f.Q, ct);
                    if (Qn.empty()) { np2.resize(K, 0); results.push_back(np2); continue; }
                    stack.push_back({std::move(Qn), std::move(np2), f.dep + 1});
                }
            }
        }
    }

    // Dedup
    std::set<std::vector<int>> seen;
    std::vector<Poly> uniq;
    for (auto& s : results) {
        s.resize(K, 0);
        if (seen.insert(s).second)
            uniq.push_back(s);
    }
    return uniq;
}

static QPoly Qshift(const QPoly& Q, int c) {
    int Ly = (int)Q.size() - 1;
    std::vector<uint8_t> pc(Ly + 1);
    pc[0] = 1;
    for (int e = 1; e <= Ly; e++) pc[e] = gf_mul(pc[e-1], (uint8_t)c);

    QPoly S(Ly + 1);
    for (int r = 0; r <= Ly; r++) {
        Poly Sr = {0};
        for (int j = r; j <= Ly; j++) {
            int bv = binom2(j, r);
            if (bv == 0) continue;
            int cf = (int)pc[j - r];
            if (cf) Sr = padd(Sr, pscalar(Q[j], cf));
        }
        S[r] = Sr;
    }

    int minv = 999999;
    for (int r = 0; r <= Ly; r++) {
        if (S[r].size() == 1 && S[r][0] == 0) continue;
        int v = 0;
        while (v < (int)S[r].size() && S[r][v] == 0) v++;
        if (v < (int)S[r].size() && r + v < minv) minv = r + v;
    }
    if (minv >= 999999) return {};

    int v = minv;
    QPoly Qn;
    for (int r = 0; r <= Ly; r++) {
        int sh = v - r;
        if (sh < 0) {
            Poly p(-sh, 0);
            p.insert(p.end(), S[r].begin(), S[r].end());
            Qn.push_back(ps(p));
        } else if (sh == 0) {
            Qn.push_back(ps(S[r]));
        } else {
            if (sh < (int)S[r].size())
                Qn.push_back(ps(Poly(S[r].begin() + sh, S[r].end())));
            else
                Qn.push_back({0});
        }
    }
    while (Qn.size() > 1 && Qn.back().size() == 1 && Qn.back()[0] == 0)
        Qn.pop_back();
    bool allz = true;
    for (auto& q : Qn) if (!(q.size() == 1 && q[0] == 0)) { allz = false; break; }
    if (allz) return {};
    return Qn;
}

// ═══════════════════════════════════════════════════════════════════════
//  Recovery helpers
// ═══════════════════════════════════════════════════════════════════════

static std::vector<int> solve_linear(
    std::vector<std::vector<int>>& A, const std::vector<int>& b)
{
    int m = (int)A.size();
    if (m == 0) return {};
    int nc = (int)A[0].size();
    // Build augmented matrix
    std::vector<std::vector<int>> aug(m);
    for (int i = 0; i < m; i++) {
        aug[i] = A[i];
        aug[i].push_back(b[i]);
    }
    for (int col = 0; col < std::min(m, nc); col++) {
        int piv = -1;
        for (int r = col; r < m; r++)
            if (aug[r][col] != 0) { piv = r; break; }
        if (piv < 0) continue;
        std::swap(aug[col], aug[piv]);
        int iv = gf_inv((uint8_t)aug[col][col]);
        for (int c2 = 0; c2 <= nc; c2++)
            aug[col][c2] = gf_mul((uint8_t)aug[col][c2], (uint8_t)iv);
        for (int r = 0; r < m; r++) {
            if (r == col) continue;
            int f = aug[r][col];
            if (f) for (int c2 = 0; c2 <= nc; c2++)
                aug[r][c2] ^= gf_mul((uint8_t)f, (uint8_t)aug[col][c2]);
        }
    }
    std::vector<int> x(std::min(m, nc));
    for (int c = 0; c < std::min(m, nc); c++) x[c] = aug[c][nc];
    return x;
}

static Poly extract_message(int n, int k, const std::vector<int>& codeword) {
    return Poly(codeword.begin() + (n - k), codeword.end());
}

static std::vector<int> decode_from_positions(
    int n, int k,
    const std::vector<int>& err_pos,
    const std::vector<int>& received)
{
    int nsym = n - k;
    int ne = (int)err_pos.size();
    if (ne == 0) {
        auto syns = rs_syndromes(n, k, received);
        bool ok = true;
        for (int s : syns) if (s != 0) { ok = false; break; }
        if (ok) return extract_message(n, k, received);
        return {};
    }
    auto syns = rs_syndromes(n, k, received);
    std::vector<int> Xlocs(ne);
    for (int i = 0; i < ne; i++) Xlocs[i] = ALPHA_POW[err_pos[i]];
    std::vector<std::vector<int>> A(ne, std::vector<int>(ne));
    for (int j = 0; j < ne; j++)
        for (int c = 0; c < ne; c++)
            A[j][c] = gf_pow((uint8_t)Xlocs[c], j);
    std::vector<int> rhs(syns.begin(), syns.begin() + ne);
    auto ev = solve_linear(A, rhs);
    if (ev.empty()) return {};
    std::vector<int> corrected(received);
    for (int i = 0; i < ne; i++)
        corrected[err_pos[i]] ^= ev[i];
    auto syn2 = rs_syndromes(n, k, corrected);
    for (int s : syn2) if (s != 0) return {};
    return extract_message(n, k, corrected);
}

// ═══════════════════════════════════════════════════════════════════════
//  Padé approximation
// ═══════════════════════════════════════════════════════════════════════

static std::vector<std::pair<Poly, Poly>> pade_approx(
    const Poly& series, int max_dl, int max_db)
{
    int Ls = pdeg(Poly(series));
    Poly mod_p(Ls + 2, 0);
    mod_p.back() = 1;
    Poly rp = mod_p, rc = ps(Poly(series));
    Poly tp = {0}, tc = {1};
    std::vector<std::pair<Poly, Poly>> results;

    while (!(rc.size() == 1 && rc[0] == 0)) {
        if (rp.size() < rc.size()) break;
        Poly q = {0}, rem = rp;
        int il = gf_inv((uint8_t)rc.back());
        while (rem.size() >= rc.size() && !(rem.size() == 1 && rem[0] == 0)) {
            int c = gf_mul((uint8_t)rem.back(), (uint8_t)il);
            int sh = (int)rem.size() - (int)rc.size();
            Poly shift(sh + 1, 0); shift[sh] = c;
            q = padd(q, shift);
            for (size_t kk = 0; kk < rc.size(); kk++)
                rem[sh + kk] ^= gf_mul((uint8_t)rc[kk], (uint8_t)c);
            rem = ps(rem);
        }
        Poly tn = padd(tp, pmul(q, tc));   // psub = padd in char 2
        Poly lam = ps(tn);
        Poly b_c = ps(rem);
        if (pdeg(lam) >= 0 && pdeg(lam) <= max_dl && pdeg(b_c) <= max_db) {
            Poly g = pgcd(lam, b_c);
            if (pdeg(g) == 0) {
                if (lam[0] != 0) {
                    int iv = gf_inv((uint8_t)lam[0]);
                    lam = pscalar(lam, iv);
                    b_c = pscalar(b_c, iv);
                }
                results.push_back({ps(lam), ps(b_c)});
            }
        }
        if (pdeg(rem) <= max_db) break;
        rp = rc; rc = rem; tp = tc; tc = tn;
    }
    return results;
}

// ═══════════════════════════════════════════════════════════════════════
//  Recovery: series -> candidates
// ═══════════════════════════════════════════════════════════════════════

static std::vector<std::vector<int>> recover_from_series(
    int n, int k,
    const Poly& series,
    const Poly& Lambda, const Poly& B,
    int L_Lam, int L_xB, int t, int t0,
    const std::vector<int>& received)
{
    Poly xB(B.size() + 1, 0);
    for (size_t i = 0; i < B.size(); i++) xB[i + 1] = B[i];

    std::vector<std::pair<Poly, Poly>> pairs;

    // Method A: BM on subsequence
    int start = std::max(0, t - L_xB + 1);
    int bm_len = 2 * (t - L_Lam);
    if (bm_len > 0 && start + bm_len <= (int)series.size()) {
        std::vector<int> sub(series.begin() + start, series.begin() + start + bm_len);
        auto [lam, dummy] = berlekamp_massey(sub);
        int trunc = std::max(t - L_xB + 1, pdeg(lam) + 1);
        Poly s_trunc(series.begin(), series.begin() + std::min(trunc, (int)series.size()));
        Poly b2 = pmul(s_trunc, lam);
        b2.resize(std::min(trunc, (int)b2.size()));
        b2 = ps(b2);
        pairs.push_back({lam, b2});
    }

    // Method B: BM on full
    auto [lam2, dummy2] = berlekamp_massey(std::vector<int>(series.begin(), series.end()));
    int trunc2 = std::max(pdeg(lam2) + 1, 1);
    Poly s_t2(series.begin(), series.begin() + std::min(trunc2, (int)series.size()));
    Poly b3 = pmul(s_t2, lam2);
    b3.resize(std::min(trunc2, (int)b3.size()));
    b3 = ps(b3);
    pairs.push_back({lam2, b3});

    // Method C: Padé
    auto pade = pade_approx(Poly(series), std::max(t - L_xB, 1), std::max(t - L_Lam, 1));
    pairs.insert(pairs.end(), pade.begin(), pade.end());

    std::vector<std::vector<int>> results;
    for (auto& [lam, b_poly] : pairs) {
        Poly Lstar = padd(pmul(Lambda, lam), pmul(xB, b_poly));
        Lstar = ps(Lstar);
        if (Lstar.size() == 1 && Lstar[0] == 0) continue;
        if (Lstar[0] != 0) {
            int iv = gf_inv((uint8_t)Lstar[0]);
            for (auto& c : Lstar) c = gf_mul((uint8_t)c, (uint8_t)iv);
        }
        auto ep = chien_search(Lstar, n);
        if ((int)ep.size() != pdeg(Lstar) || (int)ep.size() > t || ep.empty())
            continue;
        auto msg = decode_from_positions(n, k, ep, received);
        if (!msg.empty()) results.push_back(msg);
    }
    return results;
}

// ═══════════════════════════════════════════════════════════════════════
//  vec_to_Q
// ═══════════════════════════════════════════════════════════════════════

static QPoly vec_to_Q(const std::vector<int>& vec,
                      const std::vector<std::pair<int,int>>& mons, int Ly) {
    std::vector<int> mx(Ly + 1, 0);
    for (auto& [i, j] : mons)
        if (j <= Ly && i > mx[j]) mx[j] = i;
    QPoly Q(Ly + 1);
    for (int j = 0; j <= Ly; j++) Q[j].assign(mx[j] + 1, 0);
    for (int k = 0; k < (int)vec.size() && k < (int)mons.size(); k++) {
        int i = mons[k].first, j = mons[k].second;
        if (j <= Ly) Q[j][i] ^= vec[k];
    }
    for (auto& Qj : Q) Qj = ps(Qj);
    return Q;
}

// ═══════════════════════════════════════════════════════════════════════
//  wu_params
// ═══════════════════════════════════════════════════════════════════════

static py::dict wu_params_cpp(int n, int k, int L_Lam, int L_B, int t_in = -1) {
    int d = n - k + 1;
    int t0 = d / 2;
    int L_xB = L_B + 1;
    int w = L_Lam - L_xB;
    double bnd = n - std::sqrt((double)n * (k - 1));
    int tm = (t_in < 0) ? (int)std::floor(bnd - 1e-9)
                        : std::min(t_in, (int)std::floor(bnd - 1e-9));
    tm = std::max(tm, t0 + 1);
    double gap = bnd - tm;
    int m_start = (gap > 1e-9) ? (int)std::ceil((tm - t0) / gap) : 100;
    m_start = std::max(m_start, 1);
    while ((double)(tm * m_start + tm - t0) * (tm * m_start + tm - t0)
            <= 2.0 * n * m_start * (m_start + 1) * (tm - t0)) {
        m_start++;
        if (m_start > 500) break;
    }
    int Ly_den = 2 * (tm - t0);

    int best_m = -1, best_exc = 0, best_Ly = 0, best_LQ = 0;
    bool found = false;
    for (int m = m_start; m < m_start + 60; m++) {
        if (n * m * (m + 1) / 2 > 800) break;
        double Ly_opt = (Ly_den > 0) ? (double)(tm * m - tm + t0) / Ly_den : 1.0;
        for (int Ly = std::max(1, (int)Ly_opt - 1); Ly <= (int)Ly_opt + 2; Ly++) {
            int LQ = tm * m - 1 - (tm - L_Lam) * Ly;
            LQ = std::max(LQ, 0);
            if ((tm - L_Lam) * Ly + LQ >= tm * m) continue;
            int nu = 0;
            for (int j = 0; j <= Ly; j++) {
                int mx = LQ - w * j;
                if (mx >= 0) nu += mx + 1;
            }
            int nc = n * m * (m + 1) / 2;
            if (nu > nc) {
                if (!found || m < best_m) {
                    best_m = m; best_exc = nu - nc; best_Ly = Ly; best_LQ = LQ;
                    found = true;
                }
            }
        }
        if (found) break;
    }

    int m_out, Ly_out, LQ_out;
    if (found) {
        m_out = best_m; Ly_out = best_Ly; LQ_out = best_LQ;
    } else {
        m_out = m_start;
        Ly_out = (Ly_den > 0) ? std::max(1, (tm * m_out - tm + t0) / Ly_den) : 1;
        LQ_out = Ly_out * (tm - L_xB) + tm - t0 - 1;
        LQ_out = std::max(LQ_out, 0);
    }
    int Ls = std::max({3 * tm - 2 * t0 - L_Lam, 4 * (tm - t0), 2});

    py::dict result;
    result["t"] = tm; result["t0"] = t0; result["m"] = m_out;
    result["Ly"] = Ly_out; result["LQ"] = LQ_out; result["w"] = w;
    result["Ls"] = Ls; result["L_xB"] = L_xB; result["ok"] = found;
    return result;
}

// ═══════════════════════════════════════════════════════════════════════
//  Full wu_decode — the main entry point
// ═══════════════════════════════════════════════════════════════════════

static std::vector<std::vector<int>> wu_decode_cpp(
    int n, int k,
    const std::vector<int>& received,
    int t_target = -1)
{
    int nsym = n - k;
    auto syns = rs_syndromes(n, k, received);
    bool all_zero = true;
    for (int s : syns) if (s != 0) { all_zero = false; break; }
    if (all_zero) {
        auto msg = extract_message(n, k, received);
        return msg.empty() ? std::vector<std::vector<int>>{} : std::vector<std::vector<int>>{msg};
    }

    auto [Lambda, B] = berlekamp_massey(syns);
    int L_Lam = pdeg(Lambda);
    int L_B = pdeg(B);
    int L_xB = L_B + 1;

    // Try unique decode
    std::vector<int> msg_u;
    bool have_unique = false;
    if (L_Lam > 0) {
        auto ep = chien_search(Lambda, n);
        if ((int)ep.size() == L_Lam) {
            auto msg = decode_from_positions(n, k, ep, received);
            if (!msg.empty()) { msg_u = msg; have_unique = true; }
        }
    } else {
        bool ok = true;
        for (int s : syns) if (s != 0) { ok = false; break; }
        if (ok) { msg_u = extract_message(n, k, received); have_unique = true; }
    }

    if (have_unique && t_target >= 0 && t_target <= (n - k + 1) / 2)
        return {msg_u};

    auto par = wu_params_cpp(n, k, L_Lam, L_B, t_target);
    int t   = par["t"].cast<int>();
    int t0  = par["t0"].cast<int>();
    int m_v = par["m"].cast<int>();
    int Ly  = par["Ly"].cast<int>();
    int LQ  = par["LQ"].cast<int>();
    int w   = par["w"].cast<int>();
    int Ls  = par["Ls"].cast<int>();
    bool ok = par["ok"].cast<bool>();

    if (!ok) {
        double bnd = n - std::sqrt((double)n * (k - 1));
        int tma = (int)std::floor(bnd - 1e-9);
        auto par2 = wu_params_cpp(n, k, L_Lam, L_B, tma);
        if (par2["ok"].cast<bool>()) {
            par = par2;
            t   = par["t"].cast<int>();
            t0  = par["t0"].cast<int>();
            m_v = par["m"].cast<int>();
            Ly  = par["Ly"].cast<int>();
            LQ  = par["LQ"].cast<int>();
            w   = par["w"].cast<int>();
            Ls  = par["Ls"].cast<int>();
        } else {
            return have_unique ? std::vector<std::vector<int>>{msg_u}
                               : std::vector<std::vector<int>>{};
        }
    }

    if (L_Lam > t || L_xB > t)
        return have_unique ? std::vector<std::vector<int>>{msg_u}
                           : std::vector<std::vector<int>>{};

    // Rational points
    std::vector<int> xs(n), ys(n);
    std::vector<bool> isinf(n, false);
    Poly LamPoly(Lambda), BPoly(B);
    for (int i = 0; i < n; i++) {
        int xi = ALPHA_NEG[i];
        int lv = peval(LamPoly, xi);
        int bv = peval(BPoly, xi);
        int dn = gf_mul((uint8_t)xi, (uint8_t)bv);
        xs[i] = xi;
        if (dn == 0) { ys[i] = 0; isinf[i] = true; }
        else         { ys[i] = gf_div((uint8_t)lv, (uint8_t)dn); }
    }

    auto mons = monomial_list(Ly, LQ, w);
    int nu = (int)mons.size();
    int max_c = n * m_v * (m_v + 1) / 2;
    if (max_c > 2000 || nu > 2000)
        return have_unique ? std::vector<std::vector<int>>{msg_u}
                           : std::vector<std::vector<int>>{};

    auto rows = build_interp(xs, ys, isinf, m_v, mons, Ly);
    // Filter zero rows
    std::vector<std::vector<int>> nz_rows;
    for (auto& r : rows) {
        bool has_nz = false;
        for (int v : r) if (v != 0) { has_nz = true; break; }
        if (has_nz) nz_rows.push_back(std::move(r));
    }

    auto Ns = nullspace(nz_rows);
    if (Ns.empty())
        return have_unique ? std::vector<std::vector<int>>{msg_u}
                           : std::vector<std::vector<int>>{};

    std::vector<std::vector<int>> all_cands;
    int K = Ls + 1;
    int limit = std::min((int)Ns.size(), 10);
    for (int vi = 0; vi < limit; vi++) {
        auto Q = vec_to_Q(Ns[vi], mons, Ly);
        auto slist = hensel_series(Q, K, 64);
        if (slist.empty())
            slist = rr_series(Q, K, 64);

        for (auto& series : slist) {
            auto cands = recover_from_series(n, k, series, Lambda, B,
                                              L_Lam, L_xB, t, t0, received);
            all_cands.insert(all_cands.end(), cands.begin(), cands.end());
        }
        if (!all_cands.empty()) break;
    }

    if (have_unique) all_cands.push_back(msg_u);

    // Dedup
    std::set<std::vector<int>> seen;
    std::vector<std::vector<int>> out;
    for (auto& f : all_cands) {
        auto fp = f;
        fp.resize(k, 0);
        if (seen.insert(fp).second) out.push_back(fp);
    }
    return out;
}

// ═══════════════════════════════════════════════════════════════════════
//  pybind11 module definition
// ═══════════════════════════════════════════════════════════════════════

PYBIND11_MODULE(wu_core, mod) {
    gf_init();

    mod.doc() = "C++ backend for GF(2^8) Wu list decoder (hot-path acceleration)";

    // Low-level polynomial ops (useful for testing)
    mod.def("pmul", [](const Poly& a, const Poly& b) { return pmul(a, b); }, "Polynomial multiply over GF(2^8)");
    mod.def("peval", [](const Poly& a, int x) { return peval(a, x); }, "Polynomial evaluate over GF(2^8)");

    // Core building blocks
    mod.def("berlekamp_massey", [](const std::vector<int>& S) {
        auto [C, B] = berlekamp_massey(S);
        return py::make_tuple(C, B);
    }, "Berlekamp-Massey over GF(2^8)");

    mod.def("build_interp", &build_interp,
        "Build interpolation matrix (the #1 hotspot)");

    mod.def("nullspace", [](std::vector<std::vector<int>> A) {
        return nullspace(A);
    }, "Nullspace via GF(2^8) Gaussian elimination");

    mod.def("chien_search", [](const Poly& p, int n) {
        return chien_search(p, n);
    }, "Chien search for error positions");

    mod.def("hensel_series", [](const std::vector<Poly>& Q, int K, int max_roots) {
        return hensel_series(Q, K, max_roots);
    }, "Hensel lifting for power series roots",
       py::arg("Q"), py::arg("K"), py::arg("max_roots") = 64);

    mod.def("rr_series", [](const std::vector<Poly>& Q, int K, int max_br) {
        return rr_series(Q, K, max_br);
    }, "RR series (DFS fallback root finder)",
       py::arg("Q"), py::arg("K"), py::arg("max_br") = 256);

    mod.def("monomial_list", &monomial_list, "Build monomial support list");

    mod.def("vec_to_Q", [](const std::vector<int>& vec,
                           const std::vector<std::pair<int,int>>& mons, int Ly) {
        return vec_to_Q(vec, mons, Ly);
    }, "Reconstruct Q polynomial from nullspace vector");

    mod.def("wu_params", &wu_params_cpp,
        "Compute Wu decoder parameters",
        py::arg("n"), py::arg("k"), py::arg("L_Lam"), py::arg("L_B"),
        py::arg("t") = -1);

    mod.def("recover_from_series", [](int n, int k, const Poly& series,
            const Poly& Lambda, const Poly& B,
            int L_Lam, int L_xB, int t, int t0,
            const std::vector<int>& received) {
        return recover_from_series(n, k, series, Lambda, B, L_Lam, L_xB, t, t0, received);
    }, "Recover message candidates from power series");

    // The main entry point — full Wu list decode
    mod.def("wu_decode", &wu_decode_cpp,
        "Full Wu list decode over GF(2^8)",
        py::arg("n"), py::arg("k"), py::arg("received"),
        py::arg("t_target") = -1);

    // rs_syndromes for testing
    mod.def("rs_syndromes", [](int n, int k, const std::vector<int>& r) {
        return rs_syndromes(n, k, r);
    }, "Compute RS syndromes");
}
