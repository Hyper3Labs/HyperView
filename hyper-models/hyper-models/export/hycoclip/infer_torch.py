from __future__ import annotations

# ruff: noqa: I001

import argparse
import importlib
from pathlib import Path

import numpy as np

from common import add_repo_to_syspath, hyperboloid_lift, load_image_as_chw_float01


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run HyCoCLIP/MERU image embedding inference in torch.")
    p.add_argument("--hycoclip-repo", type=Path, required=True, help="Path to local clone of PalAvik/hycoclip")
    p.add_argument("--checkpoint", type=Path, required=True, help="Path to .pth checkpoint (e.g. hycoclip_vit_s.pth)")
    p.add_argument(
        "--variant",
        choices=["vit_s", "vit_b"],
        default="vit_s",
        help="ViT variant used by the checkpoint.",
    )
    p.add_argument("--image", type=Path, required=True, help="Path to an input image")
    p.add_argument("--out", type=Path, required=True, help="Output .npz path")
    p.add_argument("--device", default="cpu", help="torch device (default: cpu)")
    return p


def main() -> None:
    args = build_argparser().parse_args()

    add_repo_to_syspath(args.hycoclip_repo)

    torch = importlib.import_module("torch")
    build_timm_vit = importlib.import_module("hycoclip.encoders.image_encoders").build_timm_vit
    transformer_text_encoder_cls = (
        importlib.import_module("hycoclip.encoders.text_encoders").TransformerTextEncoder
    )
    meru_cls = importlib.import_module("hycoclip.models").MERU

    device = torch.device(args.device)

    # Build model from the upstream config defaults.
    # Note: for image embedding, HyCoCLIP vs MERU share the same `encode_image`.
    visual_arch = {
        "vit_s": "vit_small_mocov3_patch16_224",
        "vit_b": "vit_base_patch16_224",
    }[args.variant]

    visual = build_timm_vit(arch=visual_arch, global_pool="token", use_sincos2d_pos=True)
    textual = transformer_text_encoder_cls(arch="L12_W512", vocab_size=49408, context_length=77)

    model = meru_cls(
        visual=visual,
        textual=textual,
        embed_dim=512,
        curv_init=1.0,
        learn_curv=True,
        entail_weight=0.2,
    ).to(device)
    model.eval()

    ckpt = args.checkpoint.expanduser().resolve()
    if not ckpt.exists():
        raise FileNotFoundError(f"checkpoint not found: {ckpt}")

    # NOTE: HyCoCLIP checkpoints published on HF contain OmegaConf objects.
    # PyTorch >=2.6 defaults `torch.load(..., weights_only=True)` which will fail.
    # We intentionally use `weights_only=False` here; only do this for checkpoints
    # you trust.
    print("Loading checkpoint with torch.load(weights_only=False). Only do this for trusted checkpoints.")
    checkpoint_obj = torch.load(ckpt, map_location="cpu", weights_only=False)
    state_dict = checkpoint_obj["model"] if isinstance(checkpoint_obj, dict) else checkpoint_obj
    model.load_state_dict(state_dict)

    # Prepare input image.
    image_np = load_image_as_chw_float01(args.image)
    image_t = torch.from_numpy(image_np).to(device=device, dtype=torch.float32)

    with torch.inference_mode():
        space = model.encode_image(image_t, project=True)
        space_np = space.detach().to("cpu").numpy().astype(np.float32)
        curv = float(model.curv.exp().detach().to("cpu").item())

    hyper = hyperboloid_lift(space_np, curvature=curv).astype(np.float32)

    out_path = args.out.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    np.savez(
        out_path,
        space=space_np,
        hyperboloid=hyper,
        curvature=np.array(curv, dtype=np.float32),
    )

    print(f"Wrote: {out_path}")
    print(f"space shape: {space_np.shape}")
    print(f"hyperboloid shape: {hyper.shape}")
    print(f"curvature: {curv}")


if __name__ == "__main__":
    main()
