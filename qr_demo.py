#!/usr/bin/env python3
"""
qr_demo.py — Multi-version QR encoder (V1–V40) with Wu's list decoder demo.

Supports QR Versions 1–40 (21×21 to 177×177), all four ECC levels, including
multi-block configurations. Encoding is identical to paulmillr/qr: same
GF(2^8), same generator polynomial, same format/version bits, same data
placement and block interleaving.

Requires: PIL/Pillow, wu_qr.py
Optional: opencv-python (enables robust phone-photo decoding via perspective
unwarp + adaptive thresholding; falls back to a naive axis-aligned reader
when unavailable).
"""

from PIL import Image
import wu_qr as W
import random, math, os

# ═══════════════════════════════════════════════════════════════════════════════
#  QR Version Parameters (V1–V40)
#  Tables mirror wu_qr.QR_* and the QR-2005 standard.
# ═══════════════════════════════════════════════════════════════════════════════

QR_ECC_WORDS = W.QR_ECC_WORDS
QR_TOTAL = W.QR_TOTAL
QR_BLOCKS = W.QR_BLOCKS

# Alignment pattern center positions per version (Annex E, ISO/IEC 18004).
QR_ALIGN = {
    1:  [],
    2:  [6, 18],
    3:  [6, 22],
    4:  [6, 26],
    5:  [6, 30],
    6:  [6, 34],
    7:  [6, 22, 38],
    8:  [6, 24, 42],
    9:  [6, 26, 46],
    10: [6, 28, 50],
    11: [6, 30, 54],
    12: [6, 32, 58],
    13: [6, 34, 62],
    14: [6, 26, 46, 66],
    15: [6, 26, 48, 70],
    16: [6, 26, 50, 74],
    17: [6, 30, 54, 78],
    18: [6, 30, 56, 82],
    19: [6, 30, 58, 86],
    20: [6, 34, 62, 90],
    21: [6, 28, 50, 72, 94],
    22: [6, 26, 50, 74, 98],
    23: [6, 30, 54, 78, 102],
    24: [6, 28, 54, 80, 106],
    25: [6, 32, 58, 84, 110],
    26: [6, 30, 58, 86, 114],
    27: [6, 34, 62, 90, 118],
    28: [6, 26, 50, 74, 98, 122],
    29: [6, 30, 54, 78, 102, 126],
    30: [6, 26, 52, 78, 104, 130],
    31: [6, 30, 56, 82, 108, 134],
    32: [6, 34, 60, 86, 112, 138],
    33: [6, 30, 58, 86, 114, 142],
    34: [6, 34, 62, 90, 118, 146],
    35: [6, 30, 54, 78, 102, 126, 150],
    36: [6, 24, 50, 76, 102, 128, 154],
    37: [6, 28, 54, 80, 106, 132, 158],
    38: [6, 32, 58, 84, 110, 136, 162],
    39: [6, 26, 54, 82, 110, 138, 166],
    40: [6, 30, 58, 86, 114, 142, 170],
}

# BCH(18,6) generator for the V7+ version-information block.
VERSION_BCH_GEN = 0x1F25

def compute_version_bits(version):
    """Return the 18-bit version-info codeword for QR versions 7..40."""
    if version < 7:
        return None
    rem = version << 12
    for i in range(5, -1, -1):
        if rem & (1 << (i + 12)):
            rem ^= VERSION_BCH_GEN << i
    return (version << 12) | rem

# Format bits: BCH(15,5) encoding identical to paulmillr-qr
ECC_INDICATOR = {'low': 1, 'medium': 0, 'quartile': 3, 'high': 2}
FORMAT_MASK_XOR = 21522
FORMAT_GEN = 1335

def compute_format_bits(ecc_level, mask_idx):
    """Exact replica of paulmillr-qr info.formatBits()."""
    data = ECC_INDICATOR[ecc_level] << 3 | mask_idx
    d = data
    for _ in range(10):
        d = (d << 1) ^ ((d >> 9) * FORMAT_GEN)
    return (data << 10 | d) ^ FORMAT_MASK_XOR


def qr_config(version, level):
    """
    Return (n_total, k_data, ecc_words, size, max_chars) for any QR version.

    n_total is the full interleaved codeword length and k_data is the
    sum of user-data bytes across every block in the version. For multi-
    block configs ecc_words is the per-block ECC count (all blocks share it).
    Returns None for invalid versions/levels.
    """
    idx = version - 1
    if idx < 0 or idx >= len(QR_TOTAL):
        return None
    if level not in QR_ECC_WORDS:
        return None
    blocks = W.qr_block_layout(version, level)
    if not blocks:
        return None
    ecc_w = blocks[0][1]
    n_total = sum(b[0] + b[1] for b in blocks)
    k_data = sum(b[0] for b in blocks)
    size = 17 + 4 * version
    # Byte-mode header overhead: mode (4b) + count (8b for V1-9, 16b for V10+)
    # + terminator (4b). Round to bytes.
    count_bits = 8 if version <= 9 else 16
    overhead_bytes = (4 + count_bits + 4 + 7) // 8
    max_chars = max(0, k_data - overhead_bytes)
    return n_total, k_data, ecc_w, size, max_chars


def all_configs(versions=None):
    """Return list of QR configs for the given versions (default V1-V40)."""
    if versions is None:
        versions = range(1, 41)
    configs = []
    for ver in versions:
        for level in ['low', 'medium', 'quartile', 'high']:
            cfg = qr_config(ver, level)
            if cfg is None:
                continue
            n, k, ecc_w, size, max_chars = cfg
            blocks = W.qr_block_layout(ver, level)
            nb = len(blocks)
            bound_groups = W.qr_block_bound_groups(ver, level)
            worst_bound = W.qr_worst_block_bounds(ver, level)
            first_bound = W.rs_decoder_bounds(*blocks[0])
            n_b = first_bound['n']
            d_b = worst_bound['d']
            t0_b = worst_bound['t0']
            t_max_b = worst_bound['t_max']
            configs.append({
                'version': ver, 'level': level,
                'n': n, 'k': k, 'ecc_w': ecc_w,
                'size': size, 'max_chars': max_chars,
                'd': d_b, 't0': t0_b, 't_max': t_max_b,
                'blocks': blocks, 'nb': nb,
                'block_n': n_b, 'block_k': first_bound['k'],
                'block_n_max': max(g['n'] for g in bound_groups),
                'block_bounds': W.qr_block_bounds(ver, level),
                'bound_groups': bound_groups,
                'wu_range_note': (
                    ", ".join(
                        f"{g['count']}x RS({g['n']},{g['k']}): BM<={g['t0']}, Wu<={g['t_max']}"
                        for g in bound_groups
                    )
                ),
            })
    return configs

# Expose V1-High as defaults for backward compat
ECC_LEVEL = 'high'
ECC_WORDS = 17
DATA_WORDS = 9
TOTAL_WORDS = 26

# ═══════════════════════════════════════════════════════════════════════════════
#  QR Matrix Builder (V1–V40)
# ═══════════════════════════════════════════════════════════════════════════════

def _mark_function_patterns(version):
    """
    Build a (M, func) pair pre-populated with all function patterns
    (finders, alignment, timing, dark module, format-info reservation,
    version-info reservation).  Returns module values 0/1 in M and a
    boolean mask in func marking every reserved cell.
    """
    SIZE = 17 + 4 * version
    M = [[0] * SIZE for _ in range(SIZE)]
    func = [[False] * SIZE for _ in range(SIZE)]

    # ── Finder patterns (7×7 + 1-module separator) ──
    def place_finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < SIZE and 0 <= cc < SIZE):
                    continue
                if dr == -1 or dr == 7 or dc == -1 or dc == 7:
                    M[rr][cc] = 0
                elif dr == 0 or dr == 6 or dc == 0 or dc == 6:
                    M[rr][cc] = 1
                elif 2 <= dr <= 4 and 2 <= dc <= 4:
                    M[rr][cc] = 1
                else:
                    M[rr][cc] = 0
                func[rr][cc] = True

    place_finder(0, 0)
    place_finder(0, SIZE - 7)
    place_finder(SIZE - 7, 0)

    # ── Alignment patterns (V2+) ──
    # Skip any alignment whose center sits on top of a finder pattern.
    align_pos = QR_ALIGN.get(version, [])
    if len(align_pos) >= 2:
        for ar in align_pos:
            for ac in align_pos:
                if ar < 8 and ac < 8:
                    continue
                if ar < 8 and ac > SIZE - 9:
                    continue
                if ar > SIZE - 9 and ac < 8:
                    continue
                for dr in range(-2, 3):
                    for dc in range(-2, 3):
                        rr, cc = ar + dr, ac + dc
                        if 0 <= rr < SIZE and 0 <= cc < SIZE:
                            if abs(dr) == 2 or abs(dc) == 2:
                                M[rr][cc] = 1
                            elif dr == 0 and dc == 0:
                                M[rr][cc] = 1
                            else:
                                M[rr][cc] = 0
                            func[rr][cc] = True

    # ── Timing patterns ──
    for i in range(8, SIZE - 8):
        M[6][i] = 1 if i % 2 == 0 else 0
        func[6][i] = True
        M[i][6] = 1 if i % 2 == 0 else 0
        func[i][6] = True

    # ── Dark module ──
    M[SIZE - 8][8] = 1
    func[SIZE - 8][8] = True

    # ── Reserve format-info cells ──
    fmt_pos_1 = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    fmt_pos_2 = [
        (SIZE-1, 8), (SIZE-2, 8), (SIZE-3, 8), (SIZE-4, 8),
        (SIZE-5, 8), (SIZE-6, 8), (SIZE-7, 8),
        (8, SIZE-8), (8, SIZE-7), (8, SIZE-6), (8, SIZE-5),
        (8, SIZE-4), (8, SIZE-3), (8, SIZE-2), (8, SIZE-1),
    ]
    for r, c in fmt_pos_1 + fmt_pos_2:
        func[r][c] = True

    # ── Reserve version-info cells (V7+) ──
    if version >= 7:
        for i in range(18):
            a, b = i // 3, i % 3
            r1, c1 = a, SIZE - 11 + b
            r2, c2 = SIZE - 11 + b, a
            func[r1][c1] = True
            func[r2][c2] = True

    return M, func, fmt_pos_1, fmt_pos_2


def _place_format_bits(M, fbits, fmt_pos_1, fmt_pos_2):
    for i, (r, c) in enumerate(fmt_pos_1):
        M[r][c] = (fbits >> (14 - i)) & 1
    for i, (r, c) in enumerate(fmt_pos_2):
        M[r][c] = (fbits >> (14 - i)) & 1


def _place_version_bits(M, version):
    """Place 18-bit version info BCH word in top-right and bottom-left blocks."""
    if version < 7:
        return
    SIZE = len(M)
    vbits = compute_version_bits(version)
    for i in range(18):
        bit = (vbits >> i) & 1
        a, b = i // 3, i % 3
        r1, c1 = a, SIZE - 11 + b
        r2, c2 = SIZE - 11 + b, a
        M[r1][c1] = bit
        M[r2][c2] = bit


def make_qr_matrix(codewords, mask_idx=0, version=1, ecc_level='high'):
    """Build a QR matrix from codewords. Returns 2D list (0=white, 1=black)."""
    SIZE = 17 + 4 * version
    M, func, fmt_pos_1, fmt_pos_2 = _mark_function_patterns(version)

    # ── Format information (2 copies) ──
    fbits = compute_format_bits(ecc_level, mask_idx)
    _place_format_bits(M, fbits, fmt_pos_1, fmt_pos_2)

    # ── Version information (V7+) ──
    _place_version_bits(M, version)

    # ── Data placement (zigzag) ──
    bits = []
    for byte in codewords:
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)

    bit_idx = 0
    col = SIZE - 1
    going_up = True
    while col >= 0:
        if col == 6:
            col -= 1
        rows = range(SIZE - 1, -1, -1) if going_up else range(SIZE)
        for row in rows:
            for dc in [0, -1]:
                c = col + dc
                if c < 0 or c >= SIZE:
                    continue
                if func[row][c]:
                    continue
                if bit_idx < len(bits):
                    M[row][c] = bits[bit_idx] ^ _mask(mask_idx, row, c)
                    bit_idx += 1
                func[row][c] = True
        col -= 2
        going_up = not going_up

    return M


def extract_qr_data(M, mask_idx=0, version=1, ecc_level='high'):
    """Extract codeword bytes from a QR matrix (V1–V40)."""
    SIZE = 17 + 4 * version
    n_total = QR_TOTAL[version - 1]
    # Reuse the same function-pattern marker as the encoder so reservation
    # for finders, alignment, timing, format, and version info matches exactly.
    _, func, _, _ = _mark_function_patterns(version)

    # Read data bits in zigzag
    bits = []
    col = SIZE - 1
    going_up = True
    while col >= 0:
        if col == 6:
            col -= 1
        rows = range(SIZE - 1, -1, -1) if going_up else range(SIZE)
        for row in rows:
            for dc in [0, -1]:
                c = col + dc
                if c < 0 or c >= SIZE:
                    continue
                if func[row][c]:
                    continue
                bits.append(M[row][c] ^ _mask(mask_idx, row, c))
                func[row][c] = True
        col -= 2
        going_up = not going_up

    # Bits → bytes
    codewords = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for b in range(8):
            byte = (byte << 1) | bits[i + b]
        codewords.append(byte)
    return codewords[:n_total]


def _mask(idx, row, col):
    if idx == 0: return (row + col) % 2 == 0
    if idx == 1: return row % 2 == 0
    if idx == 2: return col % 3 == 0
    if idx == 3: return (row + col) % 3 == 0
    if idx == 4: return (row // 2 + col // 3) % 2 == 0
    if idx == 5: return (row * col) % 2 + (row * col) % 3 == 0
    if idx == 6: return ((row * col) % 2 + (row * col) % 3) % 2 == 0
    if idx == 7: return ((row + col) % 2 + (row * col) % 3) % 2 == 0
    return False

# ═══════════════════════════════════════════════════════════════════════════════
#  Penalty Scoring & Best Mask Selection
# ═══════════════════════════════════════════════════════════════════════════════

def penalty_score(M):
    """QR penalty score (all 4 rules)."""
    SIZE = len(M)
    penalty = 0

    # Rule 1: runs of 5+ same-color modules
    def rule1(row):
        p, run, last = 0, 1, None
        for cell in row:
            if last == cell:
                run += 1
            else:
                if run >= 5:
                    p += 3 + (run - 5)
                last = cell
                run = 1
        if run >= 5:
            p += 3 + (run - 5)
        return p

    for r in range(SIZE):
        penalty += rule1(M[r])
        penalty += rule1([M[i][r] for i in range(SIZE)])

    # Rule 2: 2×2 blocks of same color
    for r in range(SIZE - 1):
        for c in range(SIZE - 1):
            if M[r][c] == M[r][c+1] == M[r+1][c] == M[r+1][c+1]:
                penalty += 3

    # Rule 3: finder-like patterns
    p1 = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
    p2 = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
    def rule3(row):
        p = 0
        for i in range(len(row) - 10):
            sub = row[i:i+11]
            if sub == p1 or sub == p2:
                p += 40
        return p

    for r in range(SIZE):
        penalty += rule3(M[r])
        penalty += rule3([M[i][r] for i in range(SIZE)])

    # Rule 4: dark module proportion
    dark = sum(sum(row) for row in M)
    pct = (dark * 100) // (SIZE * SIZE)
    penalty += 10 * int(abs(pct - 50) / 5)

    return penalty


def get_best_qr_matrix(codewords, version=1, ecc_level='high'):
    """Try all 8 masks, return (matrix, mask_idx) with lowest penalty."""
    best_M, best_p, best_i = None, float('inf'), 0
    for i in range(8):
        M = make_qr_matrix(codewords, mask_idx=i, version=version, ecc_level=ecc_level)
        p = penalty_score(M)
        if p < best_p:
            best_M, best_p, best_i = M, p, i
    return best_M, best_i

# ═══════════════════════════════════════════════════════════════════════════════
#  Text ↔ QR Data Bytes
# ═══════════════════════════════════════════════════════════════════════════════

def qr_encode_text(text, data_words=None, max_chars=None, version=1):
    """Encode text into QR data bytes (byte mode). V10+ uses 16-bit count."""
    if data_words is None:
        data_words = DATA_WORDS
    count_bits = 8 if version <= 9 else 16
    overhead_bytes = (4 + count_bits + 4 + 7) // 8
    if max_chars is None:
        max_chars = max(0, data_words - overhead_bytes)
    text_bytes = text.encode('utf-8')[:max_chars]
    length = len(text_bytes)

    # Bit stream: mode (0100) + count + data + terminator
    bits = [0, 1, 0, 0]
    for b in range(count_bits - 1, -1, -1):
        bits.append((length >> b) & 1)
    for byte in text_bytes:
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)
    bits.extend([0, 0, 0, 0])
    while len(bits) % 8 != 0:
        bits.append(0)

    data = []
    for i in range(0, len(bits), 8):
        byte = 0
        for b in range(8):
            if i + b < len(bits):
                byte = (byte << 1) | bits[i + b]
            else:
                byte <<= 1
        data.append(byte)

    pad = [0xEC, 0x11]
    pi = 0
    while len(data) < data_words:
        data.append(pad[pi % 2])
        pi += 1
    return data[:data_words]


def qr_decode_text(data_bytes, version=1):
    """Decode QR byte-mode data back to text. V10+ uses 16-bit count."""
    bits = []
    for byte in data_bytes:
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)

    idx = 0
    mode = 0
    for _ in range(4):
        mode = (mode << 1) | bits[idx]
        idx += 1

    if mode == 0b0100:  # byte mode
        count_bits = 8 if version <= 9 else 16
        count = 0
        for _ in range(count_bits):
            count = (count << 1) | bits[idx]
            idx += 1
        chars = []
        for _ in range(count):
            byte = 0
            for _ in range(8):
                if idx < len(bits):
                    byte = (byte << 1) | bits[idx]
                    idx += 1
                else:
                    byte <<= 1
            chars.append(byte)
        return bytes(chars).decode('utf-8', errors='replace')
    return None

# ═══════════════════════════════════════════════════════════════════════════════
#  Image Rendering
# ═══════════════════════════════════════════════════════════════════════════════

def render_qr(matrix, scale=20, border=4, fg=(0, 0, 0), bg=(255, 255, 255)):
    """Render QR matrix as a PIL Image."""
    s = len(matrix)
    img_size = (s + 2 * border) * scale
    img = Image.new('RGB', (img_size, img_size), bg)
    pixels = img.load()
    for r in range(s):
        for c in range(s):
            color = fg if matrix[r][c] == 1 else bg
            for dr in range(scale):
                for dc in range(scale):
                    pr = (r + border) * scale + dr
                    pc = (c + border) * scale + dc
                    pixels[pc, pr] = color
    return img

# ═══════════════════════════════════════════════════════════════════════════════
#  QR Image Reader — image → binary matrix → codewords
# ═══════════════════════════════════════════════════════════════════════════════

# Canonical 7×7 finder pattern (1 = dark module).
_FINDER_PATTERN = [
    [1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1],
]


def _rotate_matrix_cw(matrix, k):
    """Rotate a square matrix 90° clockwise k times."""
    m = matrix
    for _ in range(k % 4):
        n = len(m)
        m = [[m[n - 1 - c][r] for c in range(n)] for r in range(n)]
    return m


def _finder_score(matrix, grid_size):
    """Sum of module matches against the three expected finder patterns
    (TL, TR, BL). Max score = 147."""
    s = 0
    for r in range(7):
        for c in range(7):
            fp = _FINDER_PATTERN[r][c]
            if matrix[r][c] == fp:
                s += 1
            if matrix[r][grid_size - 7 + c] == fp:
                s += 1
            if matrix[grid_size - 7 + r][c] == fp:
                s += 1
    return s


def _sample_matrix_vec(binary, side, grid_size):
    """Sample a grid_size×grid_size module matrix from a warped binary image
    using an integral-image box mean around each module center."""
    import numpy as np
    mod = side / grid_size
    centers = ((np.arange(grid_size) + 0.5) * mod).astype(np.int64)
    centers = np.clip(centers, 0, side - 1)
    half = max(1, int(mod * 0.3))

    # Integral image with a zero-padded top/left so box sums are O(1).
    integral = np.pad(
        np.cumsum(np.cumsum(binary.astype(np.int32), axis=0), axis=1),
        ((1, 0), (1, 0)),
        mode="constant",
    )

    rows = centers[:, None]
    cols = centers[None, :]
    y0 = np.clip(rows - half, 0, side)
    y1 = np.clip(rows + half + 1, 0, side)
    x0 = np.clip(cols - half, 0, side)
    x1 = np.clip(cols + half + 1, 0, side)

    box_sum = (
        integral[y1, x1] - integral[y0, x1] - integral[y1, x0] + integral[y0, x0]
    )
    area = (y1 - y0) * (x1 - x0)
    mean = box_sum / np.maximum(area, 1)
    return (mean > 0.5).astype(int).tolist()


def _read_qr_image_cv2(img):
    """Robust image → matrix pipeline for phone photos.

    Pipeline: cv2.QRCodeDetector locates the four QR corners → perspective
    unwarp to a fixed canonical square → adaptive thresholding → brute-force
    over (binarization × version × rotation), scoring each candidate matrix
    by how well its corners match the canonical finder pattern.

    Returns (matrix, version) or (None, None) if cv2 is unavailable or
    detection fails.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None, None

    if img.mode != "L":
        gray = np.array(img.convert("L"))
    else:
        gray = np.array(img)
    if gray.dtype != np.uint8:
        gray = gray.astype(np.uint8)

    # Try detection on a few preprocessed variants. Phone photos can be
    # low-contrast, low-resolution, or have shadows; CLAHE + upscaling +
    # sharpening noticeably improves cv2's detect() success rate.
    candidates = []
    h, w = gray.shape
    if max(h, w) < 600:
        scale = 600.0 / max(h, w)
        candidates.append(
            cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        )
    candidates.append(gray)
    try:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        candidates.append(clahe.apply(gray))
    except Exception:
        pass
    # A sharpened variant rescues some blurry / dense (high-version) QRs
    # where the classical detector silently gives up.
    try:
        sharpen_kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
        candidates.append(cv2.filter2D(gray, -1, sharpen_kernel))
    except Exception:
        pass

    # Prefer the newer Aruco-based detector when available — it's much more
    # tolerant of rotation, blur, and dense QRs than the classical one.
    detectors = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        try:
            detectors.append(cv2.QRCodeDetectorAruco())
        except Exception:
            pass
    detectors.append(cv2.QRCodeDetector())

    points = None
    used = None
    for det in detectors:
        for cand in candidates:
            try:
                ok, pts = det.detect(cand)
            except cv2.error:
                continue
            if ok and pts is not None and len(pts) > 0:
                points = pts
                used = cand
                break
        if points is not None:
            break
    if points is None:
        return None, None

    pts = np.array(points).reshape(-1, 2).astype(np.float32)
    if pts.shape[0] != 4:
        return None, None

    # Sort the four corners as TL, TR, BR, BL using the standard sum/diff trick.
    # Even if the QR is rotated, this gives a consistent permutation; the
    # subsequent 4-rotation search picks the right orientation.
    s = pts.sum(axis=1)
    d = pts[:, 0] - pts[:, 1]
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmax(d)]
    bl = pts[np.argmin(d)]
    src = np.array([tl, tr, br, bl], dtype=np.float32)

    SIDE = 600
    dst = np.array(
        [[0, 0], [SIDE - 1, 0], [SIDE - 1, SIDE - 1], [0, SIDE - 1]],
        dtype=np.float32,
    )
    H = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(
        used, H, (SIDE, SIDE), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
    )

    # Try several binarizations — phone photos sometimes need adaptive
    # thresholding for shadows, sometimes Otsu for clean lighting.
    #
    # IMPORTANT: adaptive blockSize must cover several QR modules. If it's
    # only ~1 module wide, the local mean equals the module brightness and
    # the threshold degenerates into an edge detector. SIDE=600 with V3
    # gives mod≈20px, so blockSize must be ≥ ~60. Try several sizes.
    binarizations = []
    _, otsu = cv2.threshold(
        warped, 0, 1, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
    )
    binarizations.append(otsu)
    for block in (51, 81, 121):
        binarizations.append(
            cv2.adaptiveThreshold(
                warped, 1, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, block, 7,
            )
        )

    best_matrix, best_v, best_score = None, None, -1
    for binw in binarizations:
        for v in range(1, 41):
            grid_size = 17 + 4 * v
            mod = SIDE / grid_size
            if mod < 3:
                # Need at least ~3 px per module for reliable sampling at SIDE=600.
                continue
            base = _sample_matrix_vec(binw, SIDE, grid_size)
            for k in range(4):
                rot = _rotate_matrix_cw(base, k) if k else base
                sc = _finder_score(rot, grid_size)
                if sc > best_score:
                    best_score, best_matrix, best_v = sc, rot, v

    # 147 max; require a strong finder match to avoid returning garbage.
    if best_matrix is None or best_score < 120:
        return None, None
    return best_matrix, best_v


def read_qr_image(img):
    """
    Read a QR code image and extract its binary module matrix.
    Returns (matrix, version) or (None, None) on failure.

    Tries the cv2-based pipeline first (handles rotation, perspective, and
    uneven lighting — needed for phone photos). Falls back to a naive
    axis-aligned reader if cv2 is unavailable or detection fails.
    """
    import numpy as np

    # Primary: cv2 detect → warp → adaptive threshold → finder-scored sampling.
    cv_matrix, cv_version = _read_qr_image_cv2(img)
    if cv_matrix is not None:
        return cv_matrix, cv_version

    # Fallback: original naive reader (assumes clean, axis-aligned image).
    if img.mode != 'L':
        img = img.convert('L')
    arr = np.array(img)
    h, w = arr.shape

    # Binarize with Otsu-like threshold
    thresh = (int(arr.min()) + int(arr.max())) // 2
    binary = (arr < thresh).astype(int)  # 1 = dark, 0 = light

    # Find QR bounding box (crop quiet zone)
    rows_any = np.any(binary == 1, axis=1)
    cols_any = np.any(binary == 1, axis=0)
    if not rows_any.any() or not cols_any.any():
        return None, None
    r_min, r_max = np.where(rows_any)[0][[0, -1]]
    c_min, c_max = np.where(cols_any)[0][[0, -1]]

    # Estimate module size from top-left finder pattern
    # Scan horizontal line through finder center (~row r_min + 3.5 modules)
    # The finder pattern has 1:1:3:1:1 black:white:black:white:black ratio
    module_size = _estimate_module_size(binary, r_min, c_min, r_max, c_max)
    if module_size is None or module_size < 2:
        return None, None

    # Determine grid size
    qr_pixel_w = c_max - c_min + 1
    qr_pixel_h = r_max - r_min + 1
    grid_size = round(max(qr_pixel_w, qr_pixel_h) / module_size)

    # Snap to valid QR sizes (V1=21, V2=25, ..., V40=177).
    # Each version increases the grid by 4 modules.
    version = max(1, min(40, round((grid_size - 17) / 4)))
    grid_size = 17 + 4 * version

    # Refine module size with known grid
    mod_w = qr_pixel_w / grid_size
    mod_h = qr_pixel_h / grid_size
    mod = (mod_w + mod_h) / 2

    # Sample each module at its center
    matrix = [[0] * grid_size for _ in range(grid_size)]
    for r in range(grid_size):
        for c in range(grid_size):
            # Center of module (r, c) in pixel coordinates
            py = r_min + int((r + 0.5) * mod)
            px = c_min + int((c + 0.5) * mod)
            # Sample a small area around center for robustness
            py = min(py, h - 1)
            px = min(px, w - 1)
            half = max(1, int(mod * 0.2))
            y0 = max(0, py - half); y1 = min(h, py + half + 1)
            x0 = max(0, px - half); x1 = min(w, px + half + 1)
            patch = binary[y0:y1, x0:x1]
            matrix[r][c] = 1 if patch.mean() > 0.5 else 0

    return matrix, version


def _estimate_module_size(binary, r_min, c_min, r_max, c_max):
    """Estimate module size by analyzing the top-left finder pattern."""
    h, w = binary.shape

    # Scan a horizontal line through the middle of the top-left finder
    # The finder is 7 modules tall, centered at ~r_min + 3.5*mod
    # Try multiple scan lines and pick the most consistent one
    best_mod = None
    best_score = float('inf')

    scan_range = min(r_max - r_min, c_max - c_min) // 3

    for offset in range(1, scan_range):
        scan_row = r_min + offset
        if scan_row >= h:
            continue

        # Get run-length encoding of this row
        runs = []
        current = binary[scan_row, c_min]
        count = 0
        for c in range(c_min, min(c_max + 1, w)):
            if binary[scan_row, c] == current:
                count += 1
            else:
                runs.append((current, count))
                current = binary[scan_row, c]
                count = 1
        runs.append((current, count))

        # Look for 1:1:3:1:1 dark:light:dark:light:dark pattern at start
        if len(runs) < 5:
            continue
        # First run should be dark (the finder outer edge)
        if runs[0][0] != 1:
            continue

        # Check ratio: runs[0]:runs[1]:runs[2]:runs[3]:runs[4] ≈ 1:1:3:1:1
        widths = [runs[i][1] for i in range(5)]
        total = sum(widths)
        mod_est = total / 7.0
        if mod_est < 2:
            continue

        # Check ratios
        expected = [1, 1, 3, 1, 1]
        score = sum(abs(widths[i] / mod_est - expected[i]) for i in range(5))
        if score < best_score:
            best_score = score
            best_mod = mod_est

    return best_mod


def read_qr_format_info(matrix):
    """
    Read format information from a QR matrix.
    Returns (ecc_level, mask_idx) or (None, None) on failure.
    """
    SIZE = len(matrix)

    # Read format bits from around top-left finder (positions defined by QR spec)
    fmt_pos = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)
    ]

    # Read bits (MSB first, matching our write order)
    fbits = 0
    for i, (r, c) in enumerate(fmt_pos):
        if 0 <= r < SIZE and 0 <= c < SIZE:
            fbits = (fbits << 1) | matrix[r][c]

    # Un-XOR the format mask
    raw = fbits ^ FORMAT_MASK_XOR

    # Extract ECC level (bits 13-14) and mask (bits 10-12)
    ecc_code = (raw >> 13) & 0b11
    mask_idx = (raw >> 10) & 0b111

    # Map ECC code to level name
    code_to_level = {v: k for k, v in ECC_INDICATOR.items()}
    ecc_level = code_to_level.get(ecc_code)

    if ecc_level is None:
        return None, None

    # Validate: re-compute format bits and check against read
    expected = compute_format_bits(ecc_level, mask_idx)
    if expected != fbits:
        # Try reading from the second copy (bottom-left + top-right)
        fmt_pos_2 = [
            (SIZE-1, 8), (SIZE-2, 8), (SIZE-3, 8), (SIZE-4, 8),
            (SIZE-5, 8), (SIZE-6, 8), (SIZE-7, 8),
            (8, SIZE-8), (8, SIZE-7), (8, SIZE-6), (8, SIZE-5),
            (8, SIZE-4), (8, SIZE-3), (8, SIZE-2), (8, SIZE-1)
        ]
        fbits2 = 0
        for i, (r, c) in enumerate(fmt_pos_2):
            if 0 <= r < SIZE and 0 <= c < SIZE:
                fbits2 = (fbits2 << 1) | matrix[r][c]

        raw2 = fbits2 ^ FORMAT_MASK_XOR
        ecc_code2 = (raw2 >> 13) & 0b11
        mask_idx2 = (raw2 >> 10) & 0b111
        ecc_level2 = code_to_level.get(ecc_code2)
        if ecc_level2 and compute_format_bits(ecc_level2, mask_idx2) == fbits2:
            return ecc_level2, mask_idx2

        # If neither copy validates, try all 8 masks × 4 levels (brute force)
        for lev in ['low', 'medium', 'quartile', 'high']:
            for mi in range(8):
                if compute_format_bits(lev, mi) == fbits:
                    return lev, mi
                if compute_format_bits(lev, mi) == fbits2:
                    return lev, mi

        # Last resort: return what we decoded even without validation
        return ecc_level, mask_idx

    return ecc_level, mask_idx


def decode_qr_image(img):
    """
    Full pipeline: image → matrix → format info → codewords → BM/Wu decode.
    Returns a dict with all results.
    """
    result = {
        'success': False, 'matrix': None, 'version': None,
        'level': None, 'mask': None, 'codewords': None,
        'syndromes': None, 'n_errors': 0,
        'bm_success': False, 'wu_success': False,
        'bm_text': None, 'wu_text': None,
        'error': None,
    }

    # Step 1: Read image to matrix
    matrix, version = read_qr_image(img)
    if matrix is None:
        result['error'] = "Could not detect QR code in image"
        return result
    result['matrix'] = matrix
    result['version'] = version

    # Step 2: Read format info
    ecc_level, mask_idx = read_qr_format_info(matrix)
    if ecc_level is None:
        result['error'] = f"Could not read format information (V{version})"
        return result
    result['level'] = ecc_level
    result['mask'] = mask_idx

    # Step 3: Look up the version+level layout
    cfg = qr_config(version, ecc_level)
    if cfg is None:
        result['error'] = f"V{version}-{ecc_level} is not a known QR config"
        return result

    n, k, ecc_w, size, max_chars = cfg
    blocks = W.qr_block_layout(version, ecc_level)
    nb = len(blocks)
    result['n'] = n; result['k'] = k; result['ecc_w'] = ecc_w
    result['nb'] = nb

    # Step 4: Extract codewords
    codewords = extract_qr_data(matrix, mask_idx=mask_idx, version=version, ecc_level=ecc_level)
    result['codewords'] = codewords

    # Step 5: Per-block syndromes (sum across all blocks for the summary).
    block_pairs = W.qr_de_interleave(codewords, version, ecc_level)
    all_syns = []
    nz_total = 0
    for bd, be in block_pairs:
        block_cw = list(bd) + list(be)
        s = W.qr_rs_syndromes(block_cw, ecc_w)
        all_syns.extend(s)
        nz_total += sum(1 for x in s if x != 0)
    result['syndromes'] = all_syns
    result['n_errors'] = nz_total

    # Conservative display bound across all block groups. Mixed QR layouts
    # can have different Wu radii because group 2 carries one more data byte.
    block_bounds = W.qr_block_bounds(version, ecc_level)
    bound_groups = W.qr_block_bound_groups(version, ecc_level)
    worst_bound = W.qr_worst_block_bounds(version, ecc_level)
    t0 = worst_bound['t0']
    t_max = worst_bound['t_max']
    result['t0'] = t0
    result['t_max'] = t_max
    result['block_bounds'] = block_bounds
    result['bound_groups'] = bound_groups

    if nz_total == 0:
        # All blocks clean — concatenate user data and decode text
        user_data = []
        for bd, _ in block_pairs:
            user_data.extend(bd)
        txt = qr_decode_text(user_data, version=version)
        result['success'] = True
        result['bm_success'] = True
        result['bm_text'] = txt
        result['wu_text'] = txt
        result['wu_success'] = True
        return result

    # Step 6 & 7: Per-block BM + Wu decode
    bm_data_blocks = []
    wu_data_blocks = []
    bm_all_ok = True
    wu_all_ok = True
    max_t_used = 0
    for (bd, be), block_bound in zip(block_pairs, block_bounds):
        block_cw = list(bd) + list(be)
        n_blk = len(block_cw); k_blk = len(bd); ecc_blk = len(be)
        # BM unique decode
        cw_int = W.qr_to_internal(block_cw)
        syns_int = W.rs_syndromes(n_blk, k_blk, cw_int)
        Lam, _ = W.berlekamp_massey(syns_int)
        L_Lam = W.pdeg(Lam)
        bm_decoded = None
        if all(s == 0 for s in syns_int):
            bm_decoded = list(bd)
        else:
            err_found = []
            for i in range(n_blk):
                xi = W.gf_pow(W.ALPHA, (255 - i) % 255) if i > 0 else 1
                if W.peval(Lam, xi) == 0:
                    err_found.append(i)
            if len(err_found) == L_Lam and L_Lam > 0:
                bm_msg = W.decode_from_positions(n_blk, k_blk, err_found, cw_int)
                if bm_msg:
                    bm_decoded = W.internal_msg_to_qr(bm_msg)
        if bm_decoded is None:
            bm_all_ok = False
            bm_data_blocks.append(list(bd))
        else:
            bm_data_blocks.append(bm_decoded)

        # Wu list decode (progressive t)
        wu_decoded = None
        for t_try in range(1, block_bound['t_max'] + 1):
            cands = W.qr_wu_decode(block_cw, k_blk, ecc_blk, t_target=t_try)
            if cands:
                wu_decoded = cands[0]
                max_t_used = max(max_t_used, t_try)
                break
        if wu_decoded is None:
            wu_all_ok = False
            wu_data_blocks.append(list(bd))
        else:
            wu_data_blocks.append(wu_decoded)

    if bm_all_ok:
        bm_user_data = []
        for bd in bm_data_blocks:
            bm_user_data.extend(bd)
        result['bm_success'] = True
        result['bm_text'] = qr_decode_text(bm_user_data, version=version)
        result['success'] = True

    if wu_all_ok:
        wu_user_data = []
        for bd in wu_data_blocks:
            wu_user_data.extend(bd)
        wu_txt = qr_decode_text(wu_user_data, version=version)
        result['wu_success'] = True
        result['wu_text'] = wu_txt
        result['success'] = True
        result['t_used'] = max_t_used

        # Re-encode the full message and count actual errors vs. received
        rec_cw = W.qr_rs_encode_full(wu_user_data, version, ecc_level)
        actual_errors = sum(1 for a, b in zip(rec_cw, codewords) if a != b)
        result['actual_errors'] = actual_errors

        # Build recovered matrix
        rec_qr = make_qr_matrix(rec_cw, mask_idx=mask_idx, version=version, ecc_level=ecc_level)
        result['recovered_matrix'] = rec_qr

    return result

# ═══════════════════════════════════════════════════════════════════════════════
#  Standalone Demo
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    random.seed(42)

    # Demo: V2-High gives the biggest Wu advantage (+4 beyond BM)
    version = 2
    level = 'high'
    cfg = qr_config(version, level)
    n, k, ecc_w, size, max_chars = cfg
    t0 = ecc_w // 2
    d = ecc_w + 1
    t_max = max(t0, int(math.floor(n - math.sqrt(n * max(k-1,1)) - 1e-9)))

    message = "Hello IIT-BHU!"
    t_errors = t0 + 2  # 2 beyond BM

    print("=" * 70)
    print(f"  QR V{version}-{level.upper()} Demo: Wu's List Decoder")
    print("=" * 70)
    print(f"\n  Message: \"{message}\"")
    print(f"  QR Version {version} ({size}×{size}), ECC {level.upper()}")
    print(f"  RS({n}, {k}), d={d}, BM={t0}, Wu={t_max}")
    print(f"  Injecting {t_errors} errors ({t_errors - t0} beyond BM)\n")

    # Encode
    data_bytes = qr_encode_text(message, data_words=k)
    ecc_bytes = W.qr_rs_encode(data_bytes, ecc_w)
    codeword = data_bytes + ecc_bytes

    qr_orig, mask_used = get_best_qr_matrix(codeword, version=version, ecc_level=level)
    extracted = extract_qr_data(qr_orig, mask_idx=mask_used, version=version, ecc_level=level)
    assert extracted == codeword, f"Round-trip failed!"
    print(f"  Encoded OK, mask {mask_used}, round-trip ✓")

    # Corrupt
    err_pos = sorted(random.sample(range(n), t_errors))
    corrupted_cw = codeword[:]
    for i in err_pos:
        corrupted_cw[i] ^= random.randrange(1, 256)
    qr_corrupt = make_qr_matrix(corrupted_cw, mask_idx=mask_used, version=version, ecc_level=level)

    # Decode
    cands = W.qr_wu_decode(corrupted_cw, k, ecc_w, t_target=t_errors)
    if cands and cands[0] == data_bytes:
        txt = qr_decode_text(cands[0])
        rec_ecc = W.qr_rs_encode(cands[0], ecc_w)
        qr_recovered = make_qr_matrix(cands[0] + rec_ecc, mask_idx=mask_used,
                                       version=version, ecc_level=level)
        print(f"  Wu recovered: \"{txt}\" ✓")
    else:
        qr_recovered = qr_corrupt
        print(f"  Decoding failed")

    # Save images
    out_dir = os.path.dirname(os.path.abspath(__file__))
    render_qr(qr_orig, scale=15).save(os.path.join(out_dir, 'qr_1_original.png'))
    render_qr(qr_corrupt, scale=15, fg=(180,40,40), bg=(255,230,230)).save(
        os.path.join(out_dir, 'qr_2_corrupted.png'))
    render_qr(qr_recovered, scale=15, fg=(0,100,0), bg=(230,255,230)).save(
        os.path.join(out_dir, 'qr_3_recovered.png'))
    print(f"\n  Images saved to {out_dir}")


if __name__ == "__main__":
    main()
