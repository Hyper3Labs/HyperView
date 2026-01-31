from __future__ import annotations

# ruff: noqa

import argparse
from pathlib import Path

import numpy as np

from common import load_image_as_chw_float01


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run ONNX inference for exported HyCoCLIP image encoder.")
    p.add_argument("--onnx", type=Path, required=True, help="Path to exported .onnx")
    p.add_argument("--image", type=Path, required=True, help="Path to an input image")
    p.add_argument("--out", type=Path, required=True, help="Output .npz path")
    return p


def main() -> None:
    args = build_argparser().parse_args()

    onnx_path = args.onnx.expanduser().resolve()
    if not onnx_path.exists():
        raise FileNotFoundError(f"onnx model not found: {onnx_path}")

    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])

    image_np = load_image_as_chw_float01(args.image).astype(np.float32)

    outputs = sess.run(None, {"image": image_np})
    if len(outputs) < 1:
        raise RuntimeError("ONNX session returned no outputs")

    hyper = np.asarray(outputs[0]).astype(np.float32)
    curv = None
    if len(outputs) >= 2:
        curv_arr = np.asarray(outputs[1]).astype(np.float32).reshape(-1)
        curv = float(curv_arr[0]) if curv_arr.size > 0 else None

    out_path = args.out.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Also provide space components for convenience.
    space = hyper[:, 1:].copy() if hyper.ndim == 2 and hyper.shape[1] >= 2 else None

    if space is None:
        np.savez(out_path, hyperboloid=hyper)
    elif curv is None:
        np.savez(out_path, hyperboloid=hyper, space=space)
    else:
        np.savez(out_path, hyperboloid=hyper, space=space, curvature=np.array(curv, dtype=np.float32))

    print(f"Wrote: {out_path}")
    print(f"hyperboloid shape: {hyper.shape}")
    if curv is not None:
        print(f"curvature: {curv}")


if __name__ == "__main__":
    main()
