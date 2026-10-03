"""Homography calibration for the ODIN sensor pair.

Registers the NoIR frame onto the USB webcam frame with ORB + RANSAC and
persists the result to ``matrix_h.npy`` so runtime only has to do a single
``cv2.warpPerspective``.

Diagnostics matter more than the matrix: a homography fitted on a blank
sheet of paper is garbage, and it will look perfect *on paper* while being
wrong on a real 3D subject.  This script refuses to save in that case.

Usage
-----
    python calibrate.py                      # webcam indices 1 and 0
    python calibrate.py --noir 1 --rgb 0
    python calibrate.py --pairs 40 --min-inliers 40
"""
from __future__ import annotations

import argparse
import sys
import time

import cv2
import numpy as np

DEFAULT_OUT = "matrix_h.npy"


def open_capture(src, label: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(src if isinstance(src, int) else str(src))
    if not cap.isOpened():
        raise SystemExit(f"[calibrate] cannot open {label} source: {src!r}")
    return cap


def grab(cap: cv2.VideoCapture) -> np.ndarray | None:
    ok, frame = cap.read()
    return frame if ok else None


def match_pair(noir_bgr: np.ndarray, rgb_bgr: np.ndarray, orb, matcher):
    """ORB detect + ratio-test match. Returns (pts_noir, pts_rgb)."""
    a = cv2.cvtColor(noir_bgr, cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2GRAY)
    ka, da = orb.detectAndCompute(a, None)
    kb, db = orb.detectAndCompute(b, None)
    if da is None or db is None or len(ka) < 8 or len(kb) < 8:
        return None, None
    raw = matcher.knnMatch(da, db, k=2)
    # Lowe ratio test: keep a match only if it is clearly better than 2nd.
    good = [m for m, n in raw if m.distance < 0.75 * n.distance]
    if len(good) < 8:
        return None, None
    src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    return src, dst


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--noir", default="1", help="NoIR source (index, path or URL)")
    ap.add_argument("--rgb", default="0", help="USB webcam source (index, path or URL)")
    ap.add_argument("--pairs", type=int, default=30, help="frame pairs to sample")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min-inliers", type=int, default=25,
                    help="refuse to save below this many RANSAC inliers")
    ap.add_argument("--max-reproj", type=float, default=3.0,
                    help="refuse to save above this mean reprojection error (px)")
    args = ap.parse_args()

    noir_src = int(args.noir) if str(args.noir).isdigit() else args.noir
    rgb_src = int(args.rgb) if str(args.rgb).isdigit() else args.rgb

    cap_n = open_capture(noir_src, "NoIR")
    cap_r = open_capture(rgb_src, "RGB")
    orb = cv2.ORB_create(nfeatures=1500)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)

    print("[calibrate] aiming both cameras at a TEXTURED target.")
    print("[calibrate] a checkerboard, ChArUco board or a printed noise")
    print("[calibrate] pattern all work. A blank sheet of paper does NOT:")
    print("[calibrate] ORB finds clustered keypoints and RANSAC goes degenerate.")

    src_all, dst_all = [], []
    attempts = 0
    deadline = time.time() + 60
    while len(src_all) < args.pairs and time.time() < deadline:
        attempts += 1
        noir, rgb = grab(cap_n), grab(cap_r)
        if noir is None or rgb is None:
            time.sleep(0.03)
            if time.time() > deadline:
                break
            continue
        src, dst = match_pair(noir, rgb, orb, matcher)
        if src is not None:
            src_all.append(src)
            dst_all.append(dst)
        if attempts % 15 == 0:
            print(f"[calibrate] {len(src_all)}/{args.pairs} usable pairs "
                  f"({attempts} attempts)")
        time.sleep(0.04)

    cap_n.release()
    cap_r.release()

    if len(src_all) < 4:
        print(f"[calibrate] FAIL: only {len(src_all)} usable pairs. "
              f"Not enough texture in view.", file=sys.stderr)
        return 2

    src = np.vstack(src_all)
    dst = np.vstack(dst_all)

    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    if H is None or mask is None:
        print("[calibrate] FAIL: findHomography returned no model.", file=sys.stderr)
        return 3

    inliers = int(mask.sum())
    proj = cv2.perspectiveTransform(src[mask], H)
    reproj = float(np.linalg.norm(proj - dst[mask], axis=2).mean())

    print(f"\n[calibrate] pairs sampled : {len(src_all)}")
    print(f"[calibrate] matches       : {len(src)}")
    print(f"[calibrate] RANSAC inliers: {inliers} ({100.0*inliers/len(src):.1f}%)")
    print(f"[calibrate] mean reprojection error: {reproj:.2f} px")

    if inliers < args.min_inliers:
        print(f"[calibrate] FAIL: {inliers} < --min-inliers {args.min_inliers}. "
              f"Target is under-textured; move closer or print a real pattern.",
              file=sys.stderr)
        return 4
    if reproj > args.max_reproj:
        print(f"[calibrate] FAIL: {reproj:.2f}px > --max-reproj {args.max_reproj}. "
              f"Model does not fit -- not saving.", file=sys.stderr)
        return 5

    np.save(args.out, H)
    print(f"[calibrate] saved {args.out}")
    print("[calibrate] NOTE: a homography maps a single plane exactly. It will")
    print("[calibrate] be accurate on the calibration target and degrade with")
    print("[calibrate] depth -- the two lenses are ~2.5 cm apart, so 3D subjects")
    print("[calibrate] carry parallax no H can remove. Recalibrate if the bracket")
    print("[calibrate] moves, and keep the subject inside the overlap region.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
