from __future__ import annotations

# ruff: noqa

import argparse
from pathlib import Path

import numpy as np

from common import cosine_similarity


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Compare torch vs ONNX embeddings.")
    p.add_argument("--torch", type=Path, required=True, help="Path to torch .npz output")
    p.add_argument("--onnx", type=Path, required=True, help="Path to onnx .npz output")
    p.add_argument("--cos-thresh", type=float, default=0.9999, help="Cosine similarity threshold")
    p.add_argument("--maxabs-thresh", type=float, default=1e-4, help="Max abs error threshold")
    return p


def _load_npz(path: Path) -> dict[str, np.ndarray]:
    data = np.load(path, allow_pickle=False)
    return {k: data[k] for k in data.files}


def _metrics(a: np.ndarray, b: np.ndarray) -> dict[str, float]:
    diff = a - b
    return {
        "cos": cosine_similarity(a, b),
        "max_abs": float(np.max(np.abs(diff))),
        "mean_abs": float(np.mean(np.abs(diff))),
    }


def main() -> None:
    args = build_argparser().parse_args()

    torch_path = args.torch.expanduser().resolve()
    onnx_path = args.onnx.expanduser().resolve()

    if not torch_path.exists():
        raise FileNotFoundError(f"torch output not found: {torch_path}")
    if not onnx_path.exists():
        raise FileNotFoundError(f"onnx output not found: {onnx_path}")

    t = _load_npz(torch_path)
    o = _load_npz(onnx_path)

    t_h = t.get("hyperboloid")
    o_h = o.get("hyperboloid")
    if t_h is None or o_h is None:
        raise KeyError("Both files must contain 'hyperboloid' arrays")

    if t_h.shape != o_h.shape:
        raise ValueError(f"Shape mismatch: torch {t_h.shape} vs onnx {o_h.shape}")

    # Batch metrics (flattened across batch).
    mh = _metrics(t_h.reshape(-1), o_h.reshape(-1))

    # Space-only metrics (ignore time coordinate).
    t_s = t_h[:, 1:]
    o_s = o_h[:, 1:]
    ms = _metrics(t_s.reshape(-1), o_s.reshape(-1))

    t_curv = float(np.asarray(t.get("curvature")).reshape(-1)[0]) if "curvature" in t else None
    o_curv = float(np.asarray(o.get("curvature")).reshape(-1)[0]) if "curvature" in o else None

    print("=== HyCoCLIP Torch vs ONNX ===")
    print(f"torch: {torch_path}")
    print(f"onnx : {onnx_path}")
    print("")

    print("[hyperboloid]")
    print(f"  cosine similarity : {mh['cos']:.8f}")
    print(f"  max |error|       : {mh['max_abs']:.6g}")
    print(f"  mean |error|      : {mh['mean_abs']:.6g}")

    print("[space components]")
    print(f"  cosine similarity : {ms['cos']:.8f}")
    print(f"  max |error|       : {ms['max_abs']:.6g}")
    print(f"  mean |error|      : {ms['mean_abs']:.6g}")

    if t_curv is not None or o_curv is not None:
        print("[curvature]")
        print(f"  torch: {t_curv}")
        print(f"  onnx : {o_curv}")

    ok = (mh["cos"] >= args.cos_thresh) and (mh["max_abs"] <= args.maxabs_thresh)
    if ok:
        print("\nPASS")
    else:
        print("\nFAIL")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
