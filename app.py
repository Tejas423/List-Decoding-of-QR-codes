import streamlit as st
import random
import math
import wu_qr as W
import qr_demo as Q
from PIL import Image
import io

st.set_page_config(
    page_title="QR Error Correction Showdown",
    page_icon="📶",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ──────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
    max-width: 1200px;
}

/* ── Header ── */
.hero-header {
    text-align: center;
    padding: 2.5rem 1rem 1.5rem 1rem;
    margin-bottom: 1rem;
    background: linear-gradient(135deg, rgba(99,102,241,0.12) 0%, rgba(168,85,247,0.10) 50%, rgba(236,72,153,0.08) 100%);
    border-radius: 16px;
    border: 1px solid rgba(99,102,241,0.2);
}
.hero-title {
    font-size: 2.4rem;
    font-weight: 800;
    background: linear-gradient(135deg, #818cf8, #a78bfa, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.hero-sub {
    font-size: 0.92rem;
    color: #94a3b8;
    line-height: 1.5;
    max-width: 700px;
    margin: 0 auto;
}
.hero-sub strong { color: #c4b5fd; }
.hero-badges {
    display: flex;
    justify-content: center;
    gap: 10px;
    margin-top: 1rem;
    flex-wrap: wrap;
}
.hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 600;
    border: 1px solid rgba(99,102,241,0.25);
    background: rgba(99,102,241,0.08);
    color: #a5b4fc;
}

/* ── Glass cards ── */
.glass-card {
    background: rgba(30, 32, 54, 0.6);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(99,102,241,0.15);
    border-radius: 14px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 1rem;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
}
.glass-card:hover {
    border-color: rgba(99,102,241,0.35);
    box-shadow: 0 4px 24px rgba(99,102,241,0.08);
}
.glass-card h4, .glass-card h5 {
    margin-top: 0;
}

/* ── Section headers ── */
.section-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: #818cf8;
    margin: 1.2rem 0 0.6rem 0;
}
.section-label::after {
    content: '';
    flex: 1;
    height: 1px;
    background: linear-gradient(90deg, rgba(99,102,241,0.3), transparent);
}

/* ── Capacity meter ── */
.cap-outer {
    margin: 10px 0 6px 0;
}
.cap-bar-wrap {
    position: relative;
    height: 28px;
    border-radius: 14px;
    overflow: visible;
    display: flex;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3), inset 0 1px 2px rgba(255,255,255,0.05);
}
.cap-zone-green {
    background: linear-gradient(180deg, #34d399, #059669);
    border-top-left-radius: 14px;
    border-bottom-left-radius: 14px;
}
.cap-zone-yellow {
    background: linear-gradient(180deg, #fbbf24, #d97706);
}
.cap-zone-red {
    background: linear-gradient(180deg, #f87171, #dc2626);
    border-top-right-radius: 14px;
    border-bottom-right-radius: 14px;
}
.cap-marker {
    position: absolute;
    top: -5px;
    width: 3px;
    height: 38px;
    background: #fff;
    border-radius: 2px;
    box-shadow: 0 0 8px rgba(255,255,255,0.6), 0 2px 6px rgba(0,0,0,0.4);
    z-index: 3;
}
.cap-marker-dot {
    position: absolute;
    top: -10px;
    width: 11px;
    height: 11px;
    background: #fff;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(255,255,255,0.5);
    z-index: 4;
    transform: translateX(-4px);
}
.cap-legend {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-top: 8px;
    font-size: 0.8rem;
}
.cap-legend > div {
    flex: 1;
    text-align: center;
    padding: 5px 8px;
    border-radius: 8px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.75rem;
}
.cap-legend .lg { background: rgba(5,150,105,0.15); color: #6ee7b7; border: 1px solid rgba(52,211,153,0.2); }
.cap-legend .ly { background: rgba(217,119,6,0.15); color: #fcd34d; border: 1px solid rgba(251,191,36,0.2); }
.cap-legend .lr { background: rgba(220,38,38,0.15); color: #fca5a5; border: 1px solid rgba(248,113,113,0.2); }
.cap-status {
    text-align: center;
    font-weight: 600;
    margin-top: 10px;
    font-size: 0.9rem;
    padding: 8px 16px;
    border-radius: 10px;
}

/* ── QR image frames ── */
div[data-testid="stImage"] > img {
    border-radius: 12px;
    border: 2px solid rgba(99,102,241,0.2);
    box-shadow: 0 4px 16px rgba(0,0,0,0.3);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}
div[data-testid="stImage"] > img:hover {
    transform: scale(1.02);
    box-shadow: 0 8px 28px rgba(99,102,241,0.15);
}

/* ── Metric styling ── */
div[data-testid="stMetricValue"] {
    font-size: 1.3rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}
div[data-testid="stMetricLabel"] {
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    font-size: 0.72rem;
    color: #94a3b8 !important;
}

/* ── Tabs ── */
button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.92rem;
    padding: 10px 24px;
    border-radius: 10px 10px 0 0;
}
div[data-baseweb="tab-highlight"] {
    background-color: #6366f1 !important;
}

/* ── Decoder cards ── */
.decoder-card {
    background: rgba(30, 32, 54, 0.7);
    border-radius: 14px;
    padding: 1.2rem 1.3rem;
    border: 1px solid rgba(99,102,241,0.12);
    transition: border-color 0.3s ease;
}
.decoder-card:hover {
    border-color: rgba(99,102,241,0.3);
}
.decoder-card.bm { border-left: 3px solid #6366f1; }
.decoder-card.wu { border-left: 3px solid #a855f7; }

/* ── Success/error/warning/info boxes ── */
div[data-testid="stAlert"] {
    border-radius: 10px;
    font-size: 0.88rem;
}

/* ── Expander ── */
details {
    border-radius: 10px !important;
    border-color: rgba(99,102,241,0.15) !important;
}

/* ── Buttons ── */
button[kind="secondary"] {
    border-radius: 8px;
    font-weight: 600;
}

/* ── Download button ── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #6366f1, #8b5cf6) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    padding: 0.5rem 1.5rem !important;
    transition: transform 0.15s ease, box-shadow 0.15s ease !important;
}
.stDownloadButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(99,102,241,0.3) !important;
}

/* ── Footer ── */
.app-footer {
    text-align: center;
    padding: 1.5rem 1rem;
    margin-top: 2rem;
    border-top: 1px solid rgba(99,102,241,0.15);
    font-size: 0.8rem;
    color: #64748b;
}
.app-footer a { color: #818cf8; text-decoration: none; }
.app-footer a:hover { text-decoration: underline; }

/* ── Selectbox / input ── */
div[data-baseweb="select"] > div {
    border-radius: 10px !important;
    border-color: rgba(99,102,241,0.2) !important;
}
div[data-baseweb="input"] > div {
    border-radius: 10px !important;
}

/* ── Dividers ── */
hr {
    border-color: rgba(99,102,241,0.1) !important;
    margin: 1rem 0 !important;
}

/* ── File uploader ── */
section[data-testid="stFileUploader"] {
    border-radius: 12px;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Hero header ─────────────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
    <div class="hero-title">QR Error Correction Showdown</div>
    <div class="hero-sub">
        <strong>Berlekamp–Massey</strong> vs <strong>Wu's Rational Curve-Fitting List Decoder</strong>
        <br>Reed-Solomon over GF(2⁸) · QR Versions 1–40 · Single &amp; Multi-Block
    </div>
    <div class="hero-badges">
        <span class="hero-badge">📡 Reed-Solomon</span>
        <span class="hero-badge">🧮 GF(2⁸) Arithmetic</span>
        <span class="hero-badge">📱 Phone Camera Decode</span>
        <span class="hero-badge">🔀 List Decoding</span>
    </div>
</div>
""", unsafe_allow_html=True)


def render_capacity_meter(current_errs, t0_total, t_max_total, n_total,
                          nb=1, worst_block=None, t0_blk=None, t_max_blk=None,
                          label=None):
    """Render the decoder-capability meter on the **total-error** scale."""
    total = max(n_total, t_max_total + 1, 1)
    g_pct = max(0.0, (t0_total / total) * 100)
    y_pct = max(0.0, ((t_max_total - t0_total) / total) * 100)
    r_pct = max(0.0, ((total - t_max_total) / total) * 100)
    pos_pct = min(max((current_errs / total) * 100, 0.0), 100.0)

    actual_worst = worst_block if worst_block is not None else current_errs
    blk_t0 = t0_blk if t0_blk is not None else t0_total
    blk_tmax = t_max_blk if t_max_blk is not None else t_max_total
    blk_detail = ""
    if nb > 1 and worst_block is not None:
        blk_detail = f" (worst block: {actual_worst}/{blk_t0})"

    if actual_worst <= blk_t0:
        status_bg = "rgba(5,150,105,0.12)"
        status_border = "rgba(52,211,153,0.3)"
        status_color = "#6ee7b7"
        status_icon = "✅"
        status_msg = (f"Standard decoders recover — "
                      f"{current_errs} total errors{blk_detail}")
    elif actual_worst <= blk_tmax:
        status_bg = "rgba(217,119,6,0.12)"
        status_border = "rgba(251,191,36,0.3)"
        status_color = "#fcd34d"
        status_icon = "⚠️"
        status_msg = (f"Beyond standard decoding — "
                      f"Wu list decoder recovers "
                      f"({current_errs} total errors{blk_detail})")
    else:
        status_bg = "rgba(220,38,38,0.12)"
        status_border = "rgba(248,113,113,0.3)"
        status_color = "#fca5a5"
        status_icon = "❌"
        status_msg = (f"Beyond Wu's correction radius — "
                      f"{current_errs} total errors{blk_detail})")

    label_html = ""
    if label:
        label_html = (f'<div style="font-size: 0.82rem; font-weight: 600; '
                      f'color: #94a3b8; margin-bottom: 6px; '
                      f'font-family: JetBrains Mono, monospace;">{label}</div>')

    html = f"""
    <div class="cap-outer">
      {label_html}
      <div class="cap-bar-wrap">
        <div class="cap-zone-green" style="width: {g_pct}%;"></div>
        <div class="cap-zone-yellow" style="width: {y_pct}%;"></div>
        <div class="cap-zone-red" style="width: {r_pct}%;"></div>
        <div class="cap-marker" style="left: calc({pos_pct}% - 1.5px);"></div>
        <div class="cap-marker-dot" style="left: calc({pos_pct}%);"></div>
      </div>
      <div class="cap-legend">
        <div class="lg">Standard RS · 0–{t0_total}</div>
        <div class="ly">Wu List Decoder · {t0_total + 1}–{t_max_total}</div>
        <div class="lr">Unrecoverable · {t_max_total + 1}+</div>
      </div>
      <div class="cap-status" style="color: {status_color};
           background: {status_bg}; border: 1px solid {status_border};">
        {status_icon}&nbsp;{status_msg}
      </div>
    </div>
    """
    return html


def format_bound_groups(groups):
    if not groups:
        return ""
    return "; ".join(
        f"{g['count']}× RS({g['n']},{g['k']}): BM≤{g['t0']}, Wu≤{g['t_max']}"
        for g in groups
    )


def has_mixed_bounds(bound_groups):
    """True if different block groups have different Wu radii."""
    if len(bound_groups) <= 1:
        return False
    t_maxes = set(g['t_max'] for g in bound_groups)
    t0s = set(g['t0'] for g in bound_groups)
    return len(t_maxes) > 1 or len(t0s) > 1


tab1, tab2, tab3 = st.tabs(["🎛️ Generate & Corrupt", "📤 Upload & Decode", "🔀 Ambiguous Channel"])

# ═══════════════════════════════════════════════════════════════════
#  TAB 1: Generate & Corrupt
# ═══════════════════════════════════════════════════════════════════

with tab1:
    configs = Q.all_configs()

    st.markdown('<div class="section-label">Configuration</div>', unsafe_allow_html=True)

    ctrl1, ctrl2 = st.columns([2, 1])
    with ctrl1:
        def _label(c):
            bg = c.get('bound_groups', [])
            if len(bg) > 1 and has_mixed_bounds(bg):
                blk = " + ".join(
                    f"{g['count']}×RS({g['n']},{g['k']})"
                    for g in bg
                )
            elif c['nb'] > 1:
                blk = f"{c['nb']}× RS({c['block_n']},{c['block_k']})"
            else:
                blk = f"RS({c['block_n']},{c['block_k']})"
            return (f"V{c['version']:02d}-{c['level'].upper()}  {blk}  "
                    f"RS≤{c['total_bm']}  Wu≤{c['total_wu']}  "
                    f"({c['size']}×{c['size']}, max {c['max_chars']} chars)")
        labels = [_label(c) for c in configs]
        sel_idx = st.selectbox("QR Configuration", range(len(configs)),
                               format_func=lambda i: labels[i], index=3, key="t1_cfg")
    cfg = configs[sel_idx]
    ver, level = cfg['version'], cfg['level']
    n, k, ecc_w = cfg['n'], cfg['k'], cfg['ecc_w']
    size, max_ch = cfg['size'], cfg['max_chars']
    d, t0, t_max = cfg['d'], cfg['t0'], cfg['t_max']
    total_bm, total_wu = cfg['total_bm'], cfg['total_wu']
    nb = cfg['nb']
    blocks_layout = cfg.get('blocks', W.qr_block_layout(ver, level))
    block_bounds = cfg.get('block_bounds', [])
    bound_groups = cfg.get('bound_groups', [])
    bounds_summary = format_bound_groups(bound_groups)
    mixed = has_mixed_bounds(bound_groups)

    with ctrl2:
        message = st.text_input(f"Message (max {max_ch} chars)",
                                value="Tejas"[:max_ch] if max_ch >= 5 else "Hi"[:max_ch],
                                max_chars=max_ch, key="t1_msg")

    # ── Error slider ────────────────────────────────────────────────
    st.markdown('<div class="section-label">Error Injection</div>', unsafe_allow_html=True)

    if 't1_err' in st.session_state:
        st.session_state.t1_err = max(0, min(n, st.session_state.t1_err))

    def _bump_errors(delta):
        cur = st.session_state.get('t1_err', min(total_bm + 1, n))
        st.session_state.t1_err = max(0, min(n, cur + delta))

    err_help = (
        f"Drag, click, or use the ◀/▶ buttons to set how many codeword "
        f"bytes get corrupted (out of {n}). "
        + (f"Multi-block ({nb} blocks): total capacity is "
           f"RS ≤{total_bm}, Wu ≤{total_wu} "
           f"(per-block: RS ≤{t0}, Wu ≤{t_max}). {bounds_summary}"
           if nb > 1
           else f"Single block: RS ≤{total_bm}, Wu ≤{total_wu}.")
    )

    btn_left, sl_col, btn_right = st.columns([1, 14, 1],
                                              vertical_alignment="bottom")
    with btn_left:
        st.button("◀", key="t1_dec", on_click=_bump_errors, args=(-1,),
                  help="Inject one fewer error",
                  use_container_width=True,
                  disabled=(st.session_state.get('t1_err', 0) <= 0))
    with sl_col:
        t_errors = st.slider("Byte errors to inject", 0, n,
                             min(total_bm + 1, n), help=err_help, key="t1_err")
    with btn_right:
        st.button("▶", key="t1_inc", on_click=_bump_errors, args=(1,),
                  help="Inject one more error",
                  use_container_width=True,
                  disabled=(st.session_state.get('t1_err', 0) >= n))

    # Encode
    random.seed(hash(message) & 0xFFFFFFFF)
    data_bytes = Q.qr_encode_text(message, data_words=k, version=ver)
    codeword = W.qr_rs_encode_full(data_bytes, ver, level)
    qr_orig, mask_used = Q.get_best_qr_matrix(codeword, version=ver, ecc_level=level)

    # Corrupt
    random.seed((hash(message) ^ (t_errors * 9973)) & 0xFFFFFFFF)
    err_pos = sorted(random.sample(range(n), t_errors)) if t_errors > 0 else []
    corrupted_cw = codeword[:]
    err_mags = []
    for i in err_pos:
        delta = random.randrange(1, 256); err_mags.append(delta)
        corrupted_cw[i] ^= delta
    qr_corrupt = Q.make_qr_matrix(corrupted_cw, mask_idx=mask_used, version=ver, ecc_level=level)

    # Per-block error counts
    block_pairs_orig = W.qr_de_interleave(codeword, ver, level)
    block_pairs_corr = W.qr_de_interleave(corrupted_cw, ver, level)
    per_block_errs = []
    for (bd_o, be_o), (bd_c, be_c) in zip(block_pairs_orig, block_pairs_corr):
        ne = sum(1 for a, b in zip(bd_o + be_o, bd_c + be_c) if a != b)
        per_block_errs.append(ne)
    worst_block_errs = max(per_block_errs) if per_block_errs else 0

    per_block_bm_ok = (
        all(ne <= b['t0'] for ne, b in zip(per_block_errs, block_bounds))
        if nb > 1 and block_bounds else worst_block_errs <= t0
    )
    per_block_wu_ok = (
        all(ne <= b['t_max'] for ne, b in zip(per_block_errs, block_bounds))
        if nb > 1 and block_bounds else worst_block_errs <= t_max
    )

    # Decode both
    bm_ok = wu_ok = False
    bm_text = wu_text = None
    qr_recovered = None

    if t_errors == 0:
        bm_ok = wu_ok = True
        bm_text = wu_text = message
        qr_recovered = qr_orig
    else:
        # BM unique decode per block
        bm_blocks = []
        bm_all = True
        for bd, be in block_pairs_corr:
            bcw = list(bd) + list(be)
            n_blk = len(bcw); k_blk = len(bd); ecc_blk = len(be)
            cw_int = W.qr_to_internal(bcw)
            syns_int = W.rs_syndromes(n_blk, k_blk, cw_int)
            if all(s == 0 for s in syns_int):
                bm_blocks.append(list(bd)); continue
            Lam, _ = W.berlekamp_massey(syns_int)
            L_Lam = W.pdeg(Lam)
            err_found = [i for i in range(n_blk)
                         if W.peval(Lam, W.gf_pow(W.ALPHA, (255 - i) % 255) if i > 0 else 1) == 0]
            if len(err_found) == L_Lam and L_Lam > 0:
                bm_msg = W.decode_from_positions(n_blk, k_blk, err_found, cw_int)
                if bm_msg:
                    bm_blocks.append(W.internal_msg_to_qr(bm_msg)); continue
            bm_all = False; break
        if bm_all:
            bm_decoded = []
            for bd in bm_blocks:
                bm_decoded.extend(bd)
            if bm_decoded[:k] == data_bytes[:k]:
                bm_ok = True
                bm_text = Q.qr_decode_text(bm_decoded, version=ver)

        # Wu list decode per block
        wu_cands = W.qr_wu_decode_full(corrupted_cw, ver, level)
        if wu_cands:
            wu_ok = True

    if qr_recovered is None: qr_recovered = qr_corrupt

    # Render images
    img_orig = Q.render_qr(qr_orig, scale=15)
    img_corrupt = Q.render_qr(qr_corrupt, scale=15)

    # ── Capacity meter ──────────────────────────────────────────────
    st.markdown('<div class="section-label">Decoder Capacity</div>', unsafe_allow_html=True)

    blk_label = None
    if nb > 1:
        blk_label = (
            " · ".join(
                f"{g['count']}× RS({g['n']},{g['k']})"
                for g in bound_groups
            )
            + f" — {nb} blocks"
        )

    st.markdown(
        render_capacity_meter(
            current_errs=t_errors,
            t0_total=total_bm,
            t_max_total=total_wu,
            n_total=n,
            nb=nb,
            worst_block=worst_block_errs if nb > 1 else None,
            t0_blk=t0 if nb > 1 else None,
            t_max_blk=t_max if nb > 1 else None,
            label=blk_label,
        ),
        unsafe_allow_html=True,
    )

    if nb > 1:
        st.caption(
            f"ℹ️ **Multi-block:** {nb} blocks with per-block limits "
            f"RS ≤{t0}, Wu ≤{t_max}. Total zones above are the sum across "
            f"all blocks (RS ≤{total_bm}, Wu ≤{total_wu}). "
            f"The actual boundary depends on how errors distribute across "
            f"blocks — for random errors the distribution is roughly even."
        )

    # ── Three QR codes ──────────────────────────────────────────────
    st.markdown('<div class="section-label">QR Codes</div>', unsafe_allow_html=True)
    st.caption("📱 **Tip:** every QR is rendered in pure black/white — point your "
               "phone camera at any of them to see how real scanners behave.")

    # Candidate selector (before columns so layout stays aligned)
    display_idx = 0
    if t_errors > 0 and wu_ok and len(wu_cands) > 1:
        display_idx = st.selectbox(
            f"🔀 {len(wu_cands)} candidates found — select to view:",
            range(len(wu_cands)),
            format_func=lambda i: f"Candidate {i+1}"
        )

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f"**📡 Original** · V{ver} ({size}×{size})")
        st.image(img_orig, use_container_width=True)
        st.success(f'**"{message}"** · clean codeword')
    with c2:
        st.markdown("**⚡ Corrupted**")
        st.image(img_corrupt, use_container_width=True)
        de = [p for p in err_pos if p < k]; ee = [p for p in err_pos if p >= k]
        block_note = (f" · worst block: {worst_block_errs}/{t0}"
                      if nb > 1 else "")
        if t_errors == 0:
            st.info("No errors injected.")
        elif per_block_bm_ok:
            st.warning(f"**{t_errors}** errors ({len(de)} data + {len(ee)} ECC)"
                       f" · within BM bound{block_note}")
        elif per_block_wu_ok:
            st.error(f"**{t_errors}** errors ({len(de)} data + {len(ee)} ECC)"
                     f" · beyond BM — needs Wu{block_note}")
        else:
            st.error(f"**{t_errors}** errors ({len(de)} data + {len(ee)} ECC)"
                     f" · beyond Wu bound{block_note}")
    with c3:
        st.markdown("**🔧 Recovered**")
        if t_errors == 0:
            st.image(img_orig, use_container_width=True)
            st.success("Clean — identical to original.")
        elif wu_ok:
            wu_decoded = wu_cands[display_idx]
            wu_text = Q.qr_decode_text(wu_decoded, version=ver)
            rec_cw = W.qr_rs_encode_full(wu_decoded, ver, level)
            qr_recovered = Q.make_qr_matrix(rec_cw, mask_idx=mask_used, version=ver, ecc_level=level)
            st.image(Q.render_qr(qr_recovered, scale=15), use_container_width=True)
            if wu_decoded[:k] == data_bytes[:k]:
                st.success(f'🚀 Exact match · **"{wu_text}"**')
            else:
                st.warning(f'⚠️ Alias match · **"{wu_text}"**')
        else:
            st.image(img_corrupt, use_container_width=True)
            st.error("❌ Recovery failed — showing corrupted image.")

    # ── Decoder comparison ──────────────────────────────────────────
    st.markdown('<div class="section-label">Decoder Comparison</div>', unsafe_allow_html=True)
    if nb > 1:
        st.caption(f"Multi-block layout: **{nb} blocks** · {t_errors} total errors "
                   f"(worst block: {worst_block_errs}) · "
                   f"total: RS ≤{total_bm}, Wu ≤{total_wu} · "
                   f"per-block: RS ≤{t0}, Wu ≤{t_max}")
    else:
        st.caption(f"Single block · {t_errors} errors injected · "
                   f"RS ≤{total_bm}, Wu ≤{total_wu}")

    dc1, dc2 = st.columns(2)
    with dc1:
        st.markdown("""<div class="decoder-card bm">
            <h5 style="margin:0 0 4px 0;">📐 Berlekamp–Massey</h5>
            <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:8px;">
                Classical unique decoder · used by phone scanners
            </div>
        </div>""", unsafe_allow_html=True)
        if t_errors == 0:
            st.success("No errors injected")
        elif bm_ok:
            st.success(f'✅ Decoded: **"{bm_text}"**')
        else:
            fail_detail = (f"worst block has {worst_block_errs} > {t0}"
                           if nb > 1 else f"{t_errors} > {t0}")
            st.error(f"❌ Failed — {fail_detail}")
    with dc2:
        st.markdown("""<div class="decoder-card wu">
            <h5 style="margin:0 0 4px 0;">🚀 Wu's List Decoder</h5>
            <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:8px;">
                Rational curve-fitting · ISIT 2007
            </div>
        </div>""", unsafe_allow_html=True)
        if t_errors == 0:
            st.success("No errors injected")
        elif wu_ok:
            st.success(f'🚀 Decoded: **"{wu_text}"**')
        else:
            fail_detail = (f"worst block has {worst_block_errs} > {t_max}"
                           if nb > 1 else f"{t_errors} > {t_max}")
            st.error(f"❌ Failed — {fail_detail}")

    wu_gap = total_wu - total_bm
    if bm_ok and wu_ok and t_errors > 0 and per_block_bm_ok:
        st.info(f"**Both decoders succeeded.** Wu is a strict superset — "
                f"it covers up to {total_wu} total errors, while standard RS stops at {total_bm} "
                f"(+{wu_gap} extra).")
    elif wu_ok and not bm_ok:
        st.info(f"**Only Wu succeeded.** Standard RS failed at {t_errors} errors "
                f"(total limit {total_bm}). Wu's rational interpolation "
                f"adds {wu_gap} extra errors of total correction capacity.")
    elif not wu_ok and t_errors > 0:
        st.warning(f"**Both decoders failed.** {t_errors} errors exceed "
                   f"even Wu's total capacity of {total_wu}.")

    if t_errors > 0:
        with st.expander("📦 Error Detail", expanded=False):
            st.dataframe([{"Pos": p, "Region": "DATA" if p < k else "ECC",
                          "Orig": f"0x{codeword[p]:02X}", "XOR": f"0x{err_mags[i]:02X}",
                          "Result": f"0x{corrupted_cw[p]:02X}"}
                         for i, p in enumerate(err_pos)], use_container_width=True, hide_index=True)

    st.write("")
    buf = io.BytesIO()
    Q.render_qr(qr_corrupt, scale=15, fg=(0,0,0), bg=(255,255,255)).save(buf, format='PNG')
    st.download_button(f"💾 Download Corrupted QR ({t_errors} errors)",
                       data=buf.getvalue(), file_name="corrupted_qr.png", mime="image/png")


# ═══════════════════════════════════════════════════════════════════
#  TAB 2: Upload & Decode
# ═══════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("""
    <div class="glass-card">
        <h3 style="margin-top:0;">📤 Upload a Corrupted QR Code</h3>
        <p style="color:#94a3b8; margin-bottom:8px; font-size:0.9rem;">
            Upload a QR image (V1–V40, single or multi-block) and both decoders
            will attempt recovery. Supports phone camera photos with perspective,
            rotation, and lighting distortion.
        </p>
        <p style="color:#818cf8; font-size:0.85rem; margin-bottom:0;">
            <strong>Test it:</strong> Generate &amp; Corrupt → set errors above scanner limit
            → Download → Upload here
        </p>
    </div>
    """, unsafe_allow_html=True)

    # cv2 pipeline status
    try:
        import cv2 as _cv2
        _has_aruco = hasattr(_cv2, "QRCodeDetectorAruco")
        _det_name = "Aruco detector" if _has_aruco else "classical detector"
        st.markdown(f"""<div style="display:inline-flex; align-items:center; gap:8px;
            padding:6px 14px; border-radius:8px; font-size:0.82rem; font-weight:600;
            background:rgba(5,150,105,0.1); border:1px solid rgba(52,211,153,0.2);
            color:#6ee7b7;">
            📷 Phone-photo pipeline: enabled · OpenCV {_cv2.__version__} · {_det_name}
        </div>""", unsafe_allow_html=True)
    except Exception:
        st.markdown("""<div style="display:inline-flex; align-items:center; gap:8px;
            padding:6px 14px; border-radius:8px; font-size:0.82rem; font-weight:600;
            background:rgba(220,38,38,0.1); border:1px solid rgba(248,113,113,0.2);
            color:#fca5a5;">
            📷 Phone-photo pipeline: disabled — OpenCV not available.
            Clean, axis-aligned images only.
        </div>""", unsafe_allow_html=True)

    st.write("")
    uploaded = st.file_uploader("Upload QR image", type=['png','jpg','jpeg','bmp'], key="t2_up")

    if uploaded is not None:
        img_up = Image.open(uploaded)

        uc1, uc2, uc3 = st.columns(3)
        with uc1:
            st.markdown("**📥 Uploaded**")
            st.image(img_up, use_container_width=True)

        with st.spinner("Reading QR → syndromes → BM → Wu..."):
            result = Q.decode_qr_image(img_up)

        if result['error']:
            st.error(f"❌ {result['error']}")
        else:
            cfg_u = Q.qr_config(result['version'], result['level'])
            n_u, k_u, ecc_u, size_u, _ = cfg_u
            t0_u = result.get('t0', ecc_u // 2)
            t_max_u = result.get('t_max', t0_u)
            nb_u = result.get('nb', 1)
            bound_groups_u = result.get('bound_groups', [])
            bounds_summary_u = format_bound_groups(bound_groups_u)
            syns_u = result['syndromes']
            nz_u = sum(1 for s in syns_u if s != 0) if syns_u else 0

            with uc2:
                st.markdown("**🔍 Detected**")
                st.metric("Version", f"V{result['version']}-{result['level'].upper()}")
                code_str = (f"{bounds_summary_u}, mask {result['mask']}"
                            if nb_u > 1 and bounds_summary_u
                            else f"RS({n_u},{k_u}), mask {result['mask']}")
                st.metric("Code", code_str)
            with uc3:
                st.markdown("**📊 Analysis**")
                tot_syn = ecc_u * nb_u
                st.metric("Non-zero Syndromes", f"{nz_u}/{tot_syn}")
                ae = result.get('actual_errors')
                if ae: st.metric("Errors Found", f"{ae}")
                block_bounds_u = W.qr_block_bounds(result['version'], result['level'])
                total_bm_u = sum(b['t0'] for b in block_bounds_u)
                total_wu_u = sum(b['t_max'] for b in block_bounds_u)
                st.metric("RS · Wu (total)", f"{total_bm_u} / {total_wu_u}")
                if nb_u > 1:
                    st.caption(f"Per-block: RS ≤{t0_u}, Wu ≤{t_max_u}"
                               + (f" · {bounds_summary_u}" if bounds_summary_u else ""))

            st.markdown('<div class="section-label">Decoder Results</div>', unsafe_allow_html=True)
            r1, r2 = st.columns(2)
            with r1:
                st.markdown("""<div class="decoder-card bm">
                    <h5 style="margin:0 0 4px 0;">📐 Berlekamp–Massey</h5>
                    <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:8px;">Classical unique decoder</div>
                </div>""", unsafe_allow_html=True)
                if nz_u == 0: st.success("Clean — no errors detected")
                elif result['bm_success']: st.success(f'✅ Decoded: **"{result["bm_text"]}"**')
                else: st.error("❌ Failed")
            with r2:
                st.markdown("""<div class="decoder-card wu">
                    <h5 style="margin:0 0 4px 0;">🚀 Wu's List Decoder</h5>
                    <div style="font-size:0.78rem; color:#94a3b8; margin-bottom:8px;">Rational curve-fitting · ISIT 2007</div>
                </div>""", unsafe_allow_html=True)
                if nz_u == 0: st.success("Clean — no errors detected")
                elif result['wu_success']:
                    st.success(f'🚀 Decoded: **"{result["wu_text"]}"**')
                    if ae: st.caption(f"Corrected {ae} errors (t={result.get('t_used','-')})")
                else: st.error("❌ Failed")

            if result.get('recovered_matrix'):
                st.markdown('<div class="section-label">Visual Comparison</div>', unsafe_allow_html=True)
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.markdown("**Corrupted**")
                    st.image(img_up, use_container_width=True)
                with rc2:
                    st.markdown("**Recovered**")
                    st.image(Q.render_qr(result['recovered_matrix'], scale=15,
                             fg=(0,100,0), bg=(230,255,230)), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
#  TAB 3: Ambiguous Channel
# ═══════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("""
    <div class="glass-card">
        <h3 style="margin-top:0;">🔀 Why "List" Decoding? Seeing Multiple Candidates</h3>
        <p style="color:#94a3b8; font-size:0.9rem; margin-bottom:0;">
            In Tabs 1 &amp; 2, Wu always returns <strong>exactly 1 candidate</strong> —
            so where's the "list"?
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.info(
        '**The list is a capability, not a guarantee.** For random errors, '
        'the decoded list is almost always size 1 because it\'s astronomically '
        'unlikely for two codewords to both be close to the received word.\n\n'
        'To see a genuine multi-candidate list, we need a **crafted scenario** '
        'where the received word sits in the **overlap** of two decoding spheres.'
    )

    st.markdown('<div class="section-label">How It Works</div>', unsafe_allow_html=True)
    st.markdown(
        "RS(26, 9) has minimum distance **d = 18** (MDS property: any single-byte "
        "message change flips exactly 18 codeword bytes). If we pick two messages "
        "that differ by just one character — like **\"Hi IIT!\"** vs **\"Hi IIS!\"** — "
        "their codewords C₁ and C₂ are exactly 18 bytes apart.\n\n"
        "We then construct a received word **R** by taking half the differing bytes "
        "from C₁ and half from C₂. This puts R at distance 9 from both — "
        "well within Wu's correction radius of 11."
    )

    st.markdown('<div class="section-label">Live Demo</div>', unsafe_allow_html=True)

    ac1, ac2 = st.columns(2)
    with ac1:
        msg1 = st.text_input("Message 1", value="Hi IIT!", max_chars=7, key="t3_m1")
    with ac2:
        msg2 = st.text_input("Message 2 (change 1 char)", value="Hi IIS!", max_chars=7, key="t3_m2")

    if st.button("🚀 Run Ambiguous Channel Demo", key="t3_run", use_container_width=True):
        # Encode both
        d1 = Q.qr_encode_text(msg1, data_words=9)
        d2 = Q.qr_encode_text(msg2, data_words=9)
        e1 = W.qr_rs_encode(d1, 17); c1 = d1 + e1
        e2 = W.qr_rs_encode(d2, 17); c2 = d2 + e2
        dist = sum(1 for a, b in zip(c1, c2) if a != b)

        if d1 == d2:
            st.error("Both messages encode to the same data bytes. Pick two different messages.")
        elif dist > 22:
            st.error(
                f"Codeword distance = {dist}, but need ≤ 22 (= 2 × t_max) for overlap. "
                f"Try messages that differ by fewer characters."
            )
        else:
            diff = [i for i in range(26) if c1[i] != c2[i]]
            half = len(diff) // 2
            rec = c1[:]
            for i in diff[half:]: rec[i] = c2[i]
            dr1 = sum(1 for a, b in zip(rec, c1) if a != b)
            dr2 = sum(1 for a, b in zip(rec, c2) if a != b)

            st.markdown('<div class="section-label">Geometry</div>', unsafe_allow_html=True)
            g1, g2, g3 = st.columns(3)
            g1.metric("d(C₁, C₂)", f"{dist} bytes")
            g2.metric("d(R, C₁)", f"{dr1} bytes")
            g3.metric("d(R, C₂)", f"{dr2} bytes")

            if dr1 > 11 or dr2 > 11:
                st.warning(
                    f"One distance ({max(dr1,dr2)}) exceeds Wu bound of 11. "
                    f"The codewords are too far apart for full overlap."
                )

            # Run Wu decoder
            cands = W.qr_wu_decode(rec, 9, 17, t_target=11)

            st.markdown(f'<div class="section-label">Wu\'s Output: {len(cands)} Candidate(s)</div>',
                        unsafe_allow_html=True)

            if len(cands) >= 2:
                st.success(f"🎉 **Genuine list of {len(cands)}!** This is why it's called *list* decoding.")
            elif len(cands) == 1:
                st.warning("Only 1 candidate found. The codewords may not overlap enough.")
            else:
                st.error("No candidates found.")

            for idx, cand in enumerate(cands):
                txt = Q.qr_decode_text(cand)
                is1 = cand == d1; is2 = cand == d2
                label = f'"{msg1}"' if is1 else (f'"{msg2}"' if is2 else "unknown")

                # Build QR for this candidate
                rec_ecc = W.qr_rs_encode(cand, 17)
                rec_cw = cand + rec_ecc
                _, msk = Q.get_best_qr_matrix(rec_cw, version=1, ecc_level='high')
                qr_cand = Q.make_qr_matrix(rec_cw, mask_idx=msk, version=1, ecc_level='high')
                img_cand = Q.render_qr(qr_cand, scale=15,
                                        fg=(0,100,0) if is1 else (0,0,180),
                                        bg=(230,255,230) if is1 else (230,230,255))

                cc1, cc2 = st.columns([1, 2])
                with cc1:
                    st.image(img_cand, use_container_width=True)
                with cc2:
                    match_label = "Matches Message 1" if is1 else ("Matches Message 2" if is2 else "Unknown alias")
                    st.markdown(f"**Candidate {idx+1}:** {label}")
                    st.markdown(f"**{match_label}**")
                    st.caption(f"Data: {W.fmt_hex(cand)}")

            if len(cands) >= 2:
                st.markdown('<div class="section-label">What This Means</div>', unsafe_allow_html=True)
                st.markdown(
                    "The received word R is equidistant from two valid QR codewords. "
                    "A standard BM decoder would either fail or return only one — "
                    "potentially the **wrong** one. Wu's list decoder returns **both**, "
                    "and a higher-layer protocol (like a CRC check) would pick the correct one.\n\n"
                    "In practice, random errors almost never create this situation, "
                    "which is why the list is usually size 1. But the guarantee matters: "
                    "Wu's algorithm **never misses** a valid codeword within its radius."
                )

# ── Footer ──────────────────────────────────────────────────────────
st.markdown("""
<div class="app-footer">
    Wu's ISIT 2007 rational curve-fitting list decoder over GF(2⁸) ·
    Encoding identical to paulmillr/qr · QR V1–V40 (single &amp; multi-block)
    <br>
    <span style="color:#4a5568;">Built with</span>
    <span style="color:#818cf8;">Streamlit</span> ·
    <span style="color:#4a5568;">Reed-Solomon arithmetic in pure Python</span>
</div>
""", unsafe_allow_html=True)
