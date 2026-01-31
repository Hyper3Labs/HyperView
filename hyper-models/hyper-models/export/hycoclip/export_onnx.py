from __future__ import annotations

# ruff: noqa

import argparse
import importlib
from pathlib import Path

from common import add_repo_to_syspath


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Export HyCoCLIP/MERU image encoder to ONNX.")
    p.add_argument("--hycoclip-repo", type=Path, required=True, help="Path to local clone of PalAvik/hycoclip")
    p.add_argument("--checkpoint", type=Path, required=True, help="Path to .pth checkpoint")
    p.add_argument(
        "--variant",
        choices=["vit_s", "vit_b"],
        default="vit_s",
        help="ViT variant used by the checkpoint.",
    )
    p.add_argument("--onnx", type=Path, required=True, help="Output ONNX path")
    p.add_argument("--device", default="cpu", help="torch device (default: cpu)")
    p.add_argument("--opset", type=int, default=18, help="ONNX opset version (default: 18)")
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

    class ImageEncoderWrapper(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, image):
            # image: (B,3,224,224) float32 in [0,1]
            space = self.m.encode_image(image, project=True)  # (B,D)
            curv = self.m.curv.exp().reshape(1)  # (1,)
            # Lift to full hyperboloid vector (t, x)
            x2 = (space * space).sum(dim=-1, keepdim=True)
            t = torch.sqrt((1.0 / curv) + x2)
            hyper = torch.cat([t, space], dim=-1)
            return hyper, curv

    wrapper = ImageEncoderWrapper(model).to(device)
    wrapper.eval()

    dummy = torch.zeros((1, 3, 224, 224), dtype=torch.float32, device=device)

    onnx_path = args.onnx.expanduser().resolve()
    onnx_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        wrapper,
        (dummy,),
        onnx_path,
        export_params=True,
        opset_version=args.opset,
        do_constant_folding=True,
        input_names=["image"],
        output_names=["embedding_hyperboloid", "curvature"],
        dynamic_axes={"image": {0: "batch"}, "embedding_hyperboloid": {0: "batch"}},
        training=torch.onnx.TrainingMode.EVAL,
        verbose=False,
    )

    # Normalize external data filename to match the ONNX filename + ".data"
    # This ensures compatibility when files are renamed (e.g., on HuggingFace Hub)
    onnx = importlib.import_module("onnx")
    external_data_helper = importlib.import_module("onnx.external_data_helper")

    model = onnx.load(str(onnx_path), load_external_data=True)
    external_data_helper.convert_model_to_external_data(
        model,
        all_tensors_to_one_file=True,
        location=onnx_path.name + ".data",
        size_threshold=1024,
    )
    onnx.save_model(model, str(onnx_path))

    # Remove old .data file from torch.onnx.export (if different from normalized name)
    old_data = onnx_path.with_suffix(".onnx.data")
    if old_data.exists() and old_data.name != onnx_path.name + ".data":
        old_data.unlink()

    print(f"Wrote ONNX: {onnx_path}")


if __name__ == "__main__":
    main()
