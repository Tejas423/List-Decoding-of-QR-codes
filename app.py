import streamlit as st
import random
import math
import wu_qr as W
import qr_demo as Q
from PIL import Image
import io

st.set_page_config(page_title="QR Error Correction Showdown", page_icon="📶", layout="wide")

# ── Global styling ──
st.markdown("""
<style>
  .block-container { padding-top: 2rem; }
  div[data-testid="stMetricValue"] { font-size: 1.15rem; }
  .cap-legend { display: flex; justify-content: space-between; gap: 8px;
                margin-top: 6px; font-size: 0.85rem; }
  .cap-legend > div { flex: 1; text-align: center; padding: 4px 6px;
                      border-radius: 6px; font-weight: 500; }
  .cap-status { text-align: center; font-weight: 600; margin-top: 8px;
                font-size: 0.95rem; }
</style>
""", unsafe_allow_html=True)

st.title("📶 QR Error Correction Showdown")
st.caption(
    "Berlekamp–Massey vs. Wu's Rational Curve-Fitting List Decoder  ·  "
    "Reed-Solomon over GF(2⁸)  ·  QR Versions 1–40 (single & multi-block)"
)


def render_capacity_meter(current_errs, t0, t_max, scale_max,
                          per_block=False, total_errs=None, label=None):
    """Render the decoder-capability meter as a single HTML block.

    Zones are described purely in terms of what the decoders can prove —
    not what any specific phone scanner will do in practice:
      - green  0..t0          : Berlekamp–Massey decodes uniquely
      - yellow t0+1..t_max    : beyond BM's unique-decoding bound; only a
                                 list decoder such as Wu can recover
      - red    t_max+1..      : beyond Wu's correction radius

    `current_errs` is the value the marker reflects (worst-block errors when
    per_block=True, otherwise total errors). `scale_max` is the bar's right
    edge — typically the per-block codeword length so narrow zones stay legible.
    `label` is an optional heading shown above the bar for multi-group display.
    """
    total = max(scale_max, t_max + 1, 1)
    g_pct = max(0.0, (t0 / total) * 100)
    y_pct = max(0.0, ((t_max - t0) / total) * 100)
    r_pct = max(0.0, ((total - t_max) / total) * 100)
    pos_pct = min(max((current_errs / total) * 100, 0.0), 100.0)

    unit = "errors/block" if per_block else "errors"
    if current_errs <= t0:
        status_color = "#16a34a"
        status_icon = "✅"
        status_msg = (f"BM uniquely decodes — "
                      f"{current_errs} ≤ {t0} {unit}")
    elif current_errs <= t_max:
        status_color = "#ca8a04"
        status_icon = "⚠️"
        status_msg = (f"Beyond BM's unique-decoding bound — "
                      f"only Wu list decoder recovers "
                      f"({t0} &lt; {current_errs} ≤ {t_max} {unit})")
    else:
        status_color = "#dc2626"
        status_icon = "❌"
        status_msg = (f"Beyond Wu's correction radius — "
                      f"{current_errs} &gt; {t_max} {unit}")

    if per_block and total_errs is not None and total_errs != current_errs:
        sub_text = (f"<br><span style='color:#64748b; font-weight:500; "
                    f"font-size:0.85em;'>"
                    f"{total_errs} total byte errors injected across "
                    f"all blocks · worst block in this group: {current_errs}</span>")
    else:
        sub_text = ""

    label_html = ""
    if label:
        label_html = (f'<div style="font-size: 0.85rem; font-weight: 600; '
                      f'color: #475569; margin-bottom: 4px;">{label}</div>')

    html = f"""
    <div style="margin: 6px 0 4px 0;">
      {label_html}
      <div style="position: relative; height: 32px; border-radius: 8px;
                  overflow: visible; display: flex;
                  box-shadow: 0 1px 3px rgba(0,0,0,0.15),
                              inset 0 0 0 1px rgba(0,0,0,0.1);">
        <div style="width: {g_pct}%;
                    background: linear-gradient(180deg,#86efac,#16a34a);
                    border-top-left-radius: 8px;
                    border-bottom-left-radius: 8px;"></div>
        <div style="width: {y_pct}%;
                    background: linear-gradient(180deg,#fde047,#ca8a04);"></div>
        <div style="width: {r_pct}%;
                    background: linear-gradient(180deg,#fca5a5,#dc2626);
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;"></div>
        <div style="position: absolute; left: calc({pos_pct}% - 7px);
                    top: -4px; width: 14px; height: 40px;
                    background: #0f172a; border: 2px solid white;
                    border-radius: 4px;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.45); z-index: 2;"></div>
      </div>
      <div class="cap-legend">
        <div style="background:#dcfce7; color:#166534;">
          🟢 BM recovers&nbsp;·&nbsp;0–{t0}
        </div>
        <div style="background:#fef9c3; color:#854d0e;">
          🟡 Wu only&nbsp;·&nbsp;{t0 + 1}–{t_max}
        </div>
        <div style="background:#fee2e2; color:#991b1b;">
          🔴 Beyond Wu&nbsp;·&nbsp;{t_max + 1}+
        </div>
      </div>
      <div class="cap-status" style="color: {status_color};">
        {status_icon}&nbsp;{status_msg}{sub_text}
      </div>
    </div>
    """
    return html


def render_multi_group_meters(bound_groups, per_group_worst_errs, total_errs):
    """Render per-group capacity meters for multi-block QR configs.

    When a QR layout has two groups with different Wu radii (e.g.,
    group 1: RS(44,20) Wu<=15 vs group 2: RS(45,21) Wu<=14), each group
    gets its own bar with its own marker showing the worst-block error
    count for that group. This avoids the single-bar ambiguity where
    the worst-case Wu bound can mask per-group detail.

    Returns a combined HTML string.
    """
    parts = []
    for idx, g in enumerate(bound_groups):
        worst_errs = per_group_worst_errs[idx] if idx < len(per_group_worst_errs) else 0
        label = (f"Group {idx + 1}: {g['count']}× RS({g['n']},{g['k']}) — "
                 f"BM ≤ {g['t0']}, Wu ≤ {g['t_max']}")
        parts.append(render_capacity_meter(
            current_errs=worst_errs,
            t0=g['t0'],
            t_max=g['t_max'],
            scale_max=g['n'],
            per_block=True,
            total_errs=total_errs,
            label=label,
        ))
    return '\n'.join(parts)


def format_bound_groups(groups):
    if not groups:
        return ""
    return "; ".join(
        f"{g['count']}× RS({g['n']},{g['k']}): BM≤{g['t0']}, Wu≤{g['t_max']}"
        for g in groups
    )


def compute_per_group_worst_errs(per_block_errs, blocks, bound_groups):
    """Compute the worst-block error count for each bound group.

    Maps each block to its bound group (by matching n,k,ecc) and returns
    a list of worst-error counts, one per group.
    """
    per_group = [0] * len(bound_groups)
    for bi, ne in enumerate(per_block_errs):
        if bi >= len(blocks):
            break
        bk, ecc = blocks[bi]
        bn = bk + ecc
        for gi, g in enumerate(bound_groups):
            if g['n'] == bn and g['k'] == bk and g['ecc'] == ecc:
                per_group[gi] = max(per_group[gi], ne)
                break
    return per_group


# Check whether groups have meaningfully different bounds
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
                    f"BM≤{c['t0']}  Wu≤{c['t_max']}  "
                    f"({c['size']}×{c['size']}, max {c['max_chars']} chars)")
        labels = [_label(c) for c in configs]
        sel_idx = st.selectbox("QR Configuration", range(len(configs)),
                               format_func=lambda i: labels[i], index=3, key="t1_cfg")
    cfg = configs[sel_idx]
    ver, level = cfg['version'], cfg['level']
    n, k, ecc_w = cfg['n'], cfg['k'], cfg['ecc_w']
    size, max_ch = cfg['size'], cfg['max_chars']
    d, t0, t_max = cfg['d'], cfg['t0'], cfg['t_max']
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

    # ── Error slider with ◀/▶ step buttons ─────────────────────────────
    # Clamp any stale session-state value from a prior config that may
    # exceed this config's codeword length before the slider is rendered.
    if 't1_err' in st.session_state:
        st.session_state.t1_err = max(0, min(n, st.session_state.t1_err))

    def _bump_errors(delta):
        cur = st.session_state.get('t1_err', min(t0 + 1, n))
        st.session_state.t1_err = max(0, min(n, cur + delta))

    err_help = (
        f"Drag, click, or use the ◀/▶ buttons to set how many codeword "
        f"bytes get corrupted (out of {n}). "
        + (f"Multi-block ({nb} blocks): per-block bounds are "
           f"BM ≤{t0}, conservative Wu ≤{t_max}. {bounds_summary}"
           if nb > 1
           else f"Single block: BM ≤{t0}, Wu ≤{t_max}.")
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
                             min(t0 + 1, n), help=err_help, key="t1_err")
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

    # Per-block error counts (for diagnostics + worst-block status)
    block_pairs_orig = W.qr_de_interleave(codeword, ver, level)
    block_pairs_corr = W.qr_de_interleave(corrupted_cw, ver, level)
    per_block_errs = []
    for (bd_o, be_o), (bd_c, be_c) in zip(block_pairs_orig, block_pairs_corr):
        ne = sum(1 for a, b in zip(bd_o + be_o, bd_c + be_c) if a != b)
        per_block_errs.append(ne)
    worst_block_errs = max(per_block_errs) if per_block_errs else 0

    # Per-group worst errors (for multi-group meters)
    per_group_worst = compute_per_group_worst_errs(per_block_errs, blocks_layout, bound_groups)

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

    # Render — always pure black/white
    img_orig = Q.render_qr(qr_orig, scale=15)
    img_corrupt = Q.render_qr(qr_corrupt, scale=15)
    # We will dynamically render img_rec inside column 3 below!

    # ── Capacity meter ──────────────────────────────────────────────
    st.divider()

    if nb > 1 and mixed and bound_groups:
        # Multi-group layout with DIFFERENT Wu radii → per-group bars
        st.markdown(render_multi_group_meters(
            bound_groups, per_group_worst, t_errors
        ), unsafe_allow_html=True)
        st.caption(
            f"⚠️ **Mixed block groups detected** — each group has its own "
            f"Johnson-bound Wu radius because group 2 carries one more "
            f"data byte (higher k → smaller radius). Each bar above shows "
            f"the correct bounds for its group."
        )
    elif nb > 1:
        # Multi-block but uniform bounds → single bar (worst-block marker)
        block_n_max = cfg.get('block_n_max', cfg['block_n'] + 1)
        st.markdown(
            render_capacity_meter(
                current_errs=worst_block_errs,
                t0=t0,
                t_max=t_max,
                scale_max=block_n_max,
                per_block=True,
                total_errs=t_errors,
                label=f"All {nb} blocks: RS({bound_groups[0]['n']},{bound_groups[0]['k']})" if bound_groups else None,
            ),
            unsafe_allow_html=True,
        )
    else:
        # Single block → simple bar
        st.markdown(
            render_capacity_meter(
                current_errs=t_errors,
                t0=t0,
                t_max=t_max,
                scale_max=cfg['block_n'],
                per_block=False,
                total_errs=None,
            ),
            unsafe_allow_html=True,
        )

    st.caption(
        "ℹ️ **About phone scanners:** most phones use a classical "
        "Berlekamp–Massey decoder, so they *should* succeed in the green "
        "zone and fail in yellow/red. In practice, camera thresholding "
        "can silently flip a few error bits back, so a real phone may "
        "occasionally scan past the green boundary or fail inside it. "
        "The coloured zones above reflect the **mathematical** decoder "
        "bounds, not any single scanner implementation."
    )

    # Three QR codes
    # Three QR codes
    st.divider()
    st.caption("📱 **Tip:** every QR is rendered in pure black/white so you "
               "can point your phone camera at any of them and see how real "
               "scanners behave.")

    # --- MOVE THE DROPDOWN HERE ---
    display_idx = 0
    if t_errors > 0 and wu_ok and len(wu_cands) > 1:
        display_idx = st.selectbox(
            f"🔀 {len(wu_cands)} candidates found! Select to view:", 
            range(len(wu_cands)),
            format_func=lambda i: f"Candidate {i+1}"
        )
        st.write("") # Adds a tiny bit of breathing room below the dropdown

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown(f"#### 📡 Original ({size}×{size})")
        st.image(img_orig, use_container_width=True)
        st.success(f'**"{message}"** · clean codeword')
    with c2:
        st.markdown("#### ⚡ Corrupted")
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
        st.markdown("#### 🔧 Recovered")
        
        if t_errors == 0:
            st.image(img_orig, use_container_width=True)
            st.success("Clean — identical to original.")
            
        elif wu_ok:
            # Extract the selected candidate using display_idx from above!
            wu_decoded = wu_cands[display_idx]
            wu_text = Q.qr_decode_text(wu_decoded, version=ver)
            rec_cw = W.qr_rs_encode_full(wu_decoded, ver, level)
            qr_recovered = Q.make_qr_matrix(rec_cw, mask_idx=mask_used, version=ver, ecc_level=level)
            
            # Image is now perfectly aligned with the others
            st.image(Q.render_qr(qr_recovered, scale=15), use_container_width=True)
            
            # Status Box
            if wu_decoded[:k] == data_bytes[:k]:
                st.success(f'🚀 Exact Match · **"{wu_text}"**')
                st.caption("Re-encoded from the recovered data bytes.")
            else:
                st.warning(f'⚠️ Alias Match · **"{wu_text}"**')
                st.caption("Mathematically valid codeword, but different from original data.")
                
        else:
            st.image(img_corrupt, use_container_width=True)
            st.error("❌ Recovery failed — image shown is the corrupted one.")

    # Decoder comparison
    st.divider()
    st.markdown("#### 🔬 Decoder Comparison")
    if nb > 1:
        st.caption(f"Multi-block layout: **{nb} blocks** · worst block has "
                   f"**{worst_block_errs}** errors · conservative bounds "
                   f"BM ≤{t0}, Wu ≤{t_max} · {bounds_summary}")
    else:
        st.caption(f"Single block · {t_errors} errors injected · "
                   f"BM ≤{t0}, Wu ≤{t_max}")

    dc1, dc2 = st.columns(2)
    with dc1.container(border=True):
        st.markdown("##### 📐 Berlekamp–Massey")
        st.caption("Classical unique decoder")
        if t_errors == 0:
            st.success("No errors injected")
        elif bm_ok:
            st.success(f'✅ Decoded: **"{bm_text}"**')
        else:
            st.error(f"❌ Failed — worst block has {worst_block_errs} > {t0}")
    with dc2.container(border=True):
        st.markdown("##### 🚀 Wu's List Decoder")
        st.caption("Rational curve-fitting (ISIT 2007)")
        if t_errors == 0:
            st.success("No errors injected")
        elif wu_ok:
            st.success(f'🚀 Decoded: **"{wu_text}"**')
        else:
            st.error(f"❌ Failed — worst block has {worst_block_errs} > {t_max}")

    if bm_ok and wu_ok and t_errors > 0 and per_block_bm_ok:
        st.info(f"**Both decoders succeeded.** Wu is a strict superset — "
                f"it covers every block group up to {t_max} errors, while BM stops at {t0}.")
    elif wu_ok and not bm_ok:
        gap = t_max - t0
        st.info(f"**Only Wu succeeded.** BM failed at {worst_block_errs} errors "
                f"in the worst block (limit {t0}). Wu's rational interpolation "
                f"adds {gap} extra errors of correction per block.")
    elif not wu_ok and t_errors > 0:
        st.warning(f"**Both decoders failed.** {worst_block_errs} errors in the "
                   f"worst block exceed the conservative Wu bound of {t_max}.")

    if t_errors > 0:
        with st.expander("📦 Detail", expanded=False):
            st.dataframe([{"Pos": p, "Region": "DATA" if p < k else "ECC",
                          "Orig": f"0x{codeword[p]:02X}", "XOR": f"0x{err_mags[i]:02X}",
                          "Result": f"0x{corrupted_cw[p]:02X}"}
                         for i, p in enumerate(err_pos)], use_container_width=True, hide_index=True)

    st.divider()
    buf = io.BytesIO()
    Q.render_qr(qr_corrupt, scale=15, fg=(0,0,0), bg=(255,255,255)).save(buf, format='PNG')
    st.download_button(f"💾 Download corrupted QR ({t_errors} errors)",
                       data=buf.getvalue(), file_name="corrupted_qr.png", mime="image/png")


# ═══════════════════════════════════════════════════════════════════
#  TAB 2: Upload & Decode
# ═══════════════════════════════════════════════════════════════════

with tab2:
    st.markdown("""
    ### 📤 Upload a Corrupted QR Code
    Upload a QR image (V1–V40, single or multi-block) and both decoders will attempt recovery.

    **Test it:** Generate & Corrupt → set errors above scanner limit → Download → Upload here
    """)

    uploaded = st.file_uploader("Upload QR image", type=['png','jpg','jpeg','bmp'], key="t2_up")

    if uploaded is not None:
        img_up = Image.open(uploaded)
        st.divider()
        uc1, uc2, uc3 = st.columns(3)
        with uc1:
            st.markdown("##### 📥 Uploaded")
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
                st.markdown("##### 🔍 Detected")
                st.metric("Version", f"V{result['version']}-{result['level'].upper()}")
                code_str = (f"{bounds_summary_u}, mask {result['mask']}"
                            if nb_u > 1 and bounds_summary_u
                            else f"RS({n_u},{k_u}), mask {result['mask']}")
                st.metric("Code", code_str)
            with uc3:
                st.markdown("##### 📊 Analysis")
                tot_syn = ecc_u * nb_u
                st.metric("Non-zero Syndromes", f"{nz_u}/{tot_syn}")
                ae = result.get('actual_errors')
                if ae: st.metric("Errors Found", f"{ae}")
                limits_label = "BM/blk · Wu/blk" if nb_u > 1 else "BM · Wu"
                st.metric(limits_label, f"{t0_u} / {t_max_u}")
                if nb_u > 1 and bounds_summary_u:
                    st.caption(f"Limiting bounds shown. Groups: {bounds_summary_u}")

            st.divider()
            r1, r2 = st.columns(2)
            with r1.container(border=True):
                st.markdown("##### 📐 Berlekamp–Massey")
                st.caption("Classical unique decoder")
                if nz_u == 0: st.success("Clean — no errors detected")
                elif result['bm_success']: st.success(f'✅ Decoded: **"{result["bm_text"]}"**')
                else: st.error("❌ Failed")
            with r2.container(border=True):
                st.markdown("##### 🚀 Wu's List Decoder")
                st.caption("Rational curve-fitting (ISIT 2007)")
                if nz_u == 0: st.success("Clean — no errors detected")
                elif result['wu_success']:
                    st.success(f'🚀 Decoded: **"{result["wu_text"]}"**')
                    if ae: st.caption(f"Corrected {ae} errors (t={result.get('t_used','-')})")
                else: st.error("❌ Failed")

            if result.get('recovered_matrix'):
                st.divider()
                rc1, rc2 = st.columns(2)
                with rc1:
                    st.markdown("##### Corrupted")
                    st.image(img_up, use_container_width=True)
                with rc2:
                    st.markdown("##### Recovered")
                    st.image(Q.render_qr(result['recovered_matrix'], scale=15,
                             fg=(0,100,0), bg=(230,255,230)), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
#  TAB 3: Ambiguous Channel — genuine LIST with multiple candidates
# ═══════════════════════════════════════════════════════════════════

with tab3:
    st.markdown("""
    ### 🔀 Why "List" Decoding? Seeing Multiple Candidates
    
    In Tabs 1 & 2, Wu always returns **exactly 1 candidate** — 
    so where's the "list"?
    """)

    st.info(
        '**The list is a capability, not a guarantee.** For random errors, '
        'the decoded list is almost always size 1 because it\'s astronomically '
        'unlikely for two codewords to both be close to the received word.\n\n'
        'To see a genuine multi-candidate list, we need a **crafted scenario** '
        'where the received word sits in the **overlap** of two decoding spheres.'
    )

    st.markdown("---")
    st.markdown("#### How it works")
    st.markdown(
        "RS(26, 9) has minimum distance **d = 18** (MDS property: any single-byte "
        "message change flips exactly 18 codeword bytes). If we pick two messages "
        "that differ by just one character — like **\"Hi IIT!\"** vs **\"Hi IIS!\"** — "
        "their codewords C₁ and C₂ are exactly 18 bytes apart.\n\n"
        "We then construct a received word **R** by taking half the differing bytes "
        "from C₁ and half from C₂. This puts R at distance 9 from both — "
        "well within Wu's correction radius of 11."
    )

    st.markdown("---")
    st.markdown("#### Live Demo")

    ac1, ac2 = st.columns(2)
    with ac1:
        msg1 = st.text_input("Message 1", value="Hi IIT!", max_chars=7, key="t3_m1")
    with ac2:
        msg2 = st.text_input("Message 2 (change 1 char)", value="Hi IIS!", max_chars=7, key="t3_m2")

    if st.button("Run Ambiguous Channel Demo", key="t3_run"):
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

            st.markdown("##### Geometry")
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

            st.divider()
            st.markdown(f"##### Wu's Decoder Output: **{len(cands)} candidate(s)**")

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

                st.markdown(f"---")
                cc1, cc2 = st.columns([1, 2])
                with cc1:
                    st.image(img_cand, use_container_width=True)
                with cc2:
                    match_label = "Matches Message 1" if is1 else ("Matches Message 2" if is2 else "Unknown alias")
                    st.markdown(f"**Candidate {idx+1}:** {label}")
                    st.markdown(f"**{match_label}**")
                    st.caption(f"Data: {W.fmt_hex(cand)}")

            if len(cands) >= 2:
                st.divider()
                st.markdown(
                    "#### What this means\n\n"
                    "The received word R is equidistant from two valid QR codewords. "
                    "A standard BM decoder would either fail or return only one — "
                    "potentially the **wrong** one. Wu's list decoder returns **both**, "
                    "and a higher-layer protocol (like a CRC check) would pick the correct one.\n\n"
                    "In practice, random errors almost never create this situation, "
                    "which is why the list is usually size 1. But the guarantee matters: "
                    "Wu's algorithm **never misses** a valid codeword within its radius."
                )

# Footer
st.divider()
st.caption(
    "Wu's ISIT 2007 rational curve-fitting list decoder over GF(2⁸) · "
    "Encoding identical to paulmillr/qr · QR V1–V40 (single & multi-block)"
)
