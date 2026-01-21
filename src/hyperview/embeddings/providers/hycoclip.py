"""Clean HyCoCLIP embedding provider (PyTorch) - no external hycoclip package.

This is a minimal reimplementation that loads HyCoCLIP weights directly.
Only depends on torch, timm, and numpy.

Architecture:
- ViT backbone (timm)
- Linear projection to embedding space
- Exponential map to hyperboloid (Lorentz model)

Checkpoints: https://huggingface.co/avik-pal/hycoclip

Requirements:
    uv sync --extra ml
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from hyperview.core.sample import Sample
from hyperview.embeddings.providers import (
    BaseEmbeddingProvider,
    ModelSpec,
    register_provider,
)

__all__ = ["HyCoCLIPProvider"]


# -----------------------------------------------------------------------------
# Known checkpoints (auto-download from HuggingFace)
# -----------------------------------------------------------------------------

HYCOCLIP_CHECKPOINTS: dict[str, str] = {
    "hycoclip_vit_s": "hf://avik-pal/hycoclip#hycoclip_vit_s.pth",
    "hycoclip_vit_b": "hf://avik-pal/hycoclip#hycoclip_vit_b.pth",
    "meru_vit_s": "hf://avik-pal/hycoclip#meru_vit_s.pth",
    "meru_vit_b": "hf://avik-pal/hycoclip#meru_vit_b.pth",
}


# -----------------------------------------------------------------------------
# Hyperboloid math
# -----------------------------------------------------------------------------


def _exp_map_lorentz(x: "torch.Tensor", c: float) -> "torch.Tensor":
    """Exponential map from tangent space at the hyperboloid vertex.

    Maps Euclidean tangent vectors at the origin onto the Lorentz (hyperboloid)
    model of hyperbolic space with curvature -c.

    Output is ordered as (t, x1, ..., xD) and satisfies:
        t^2 - ||x||^2 = 1/c

    This matches HyCoCLIP/MERU exp_map0 numerics by clamping the sinh input for
    stability and inferring the time component from the hyperboloid constraint.

    Args:
        x: Euclidean tangent vectors at the origin, shape (..., D).
        c: Positive curvature parameter (hyperbolic curvature is -c).

    Returns:
        Hyperboloid coordinates, shape (..., D + 1).
    """
    import torch

    if c <= 0:
        raise ValueError(f"curvature c must be > 0, got {c}")

    # Compute in float32 under AMP to avoid float16/bfloat16 overflow.
    if x.dtype in (torch.float16, torch.bfloat16):
        x = x.float()

    sqrt_c = math.sqrt(c)
    rc_xnorm = sqrt_c * torch.norm(x, dim=-1, keepdim=True)

    eps = 1e-8
    sinh_input = torch.clamp(rc_xnorm, min=eps, max=math.asinh(2**15))
    spatial = torch.sinh(sinh_input) * x / torch.clamp(rc_xnorm, min=eps)

    t = torch.sqrt((1.0 / c) + torch.sum(spatial * spatial, dim=-1, keepdim=True))
    return torch.cat([t, spatial], dim=-1)

# -----------------------------------------------------------------------------
# ViT Image Encoder
# -----------------------------------------------------------------------------


def _create_encoder(
    embed_dim: int = 512,
    curvature: float = 0.1,
    vit_model: str = "vit_small_patch16_224",
) -> "nn.Module":
    """Create HyCoCLIP image encoder using timm ViT backbone."""
    import timm
    import torch.nn as nn

    class HyCoCLIPImageEncoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.backbone = timm.create_model(vit_model, pretrained=False, num_classes=0)
            backbone_dim = int(getattr(self.backbone, "embed_dim"))
            self.proj = nn.Linear(backbone_dim, embed_dim, bias=False)
            self.curvature = curvature
            self.embed_dim = embed_dim

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            features = self.backbone(x)
            spatial = self.proj(features)
            return _exp_map_lorentz(spatial, self.curvature)

    return HyCoCLIPImageEncoder()


def _load_encoder(checkpoint_path: str, device: str = "cpu") -> Any:
    """Load HyCoCLIP image encoder from checkpoint."""
    import torch

    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    state = ckpt["model"]

    # Extract curvature (stored as log)
    curvature = torch.exp(state["curv"]).item()

    # Determine model variant from checkpoint
    proj_shape = state["visual_proj.weight"].shape
    embed_dim = proj_shape[0]
    backbone_dim = proj_shape[1]

    vit_models = {
        384: "vit_small_patch16_224",
        768: "vit_base_patch16_224",
        1024: "vit_large_patch16_224",
    }
    vit_model = vit_models.get(backbone_dim, "vit_small_patch16_224")

    model = _create_encoder(embed_dim=embed_dim, curvature=curvature, vit_model=vit_model)

    # Remap checkpoint keys
    new_state = {}
    for key, value in state.items():
        if key.startswith("visual."):
            new_state["backbone." + key[7:]] = value
        elif key == "visual_proj.weight":
            new_state["proj.weight"] = value

    model.load_state_dict(new_state, strict=False)
    return model.to(device).eval()


# -----------------------------------------------------------------------------
# Provider
# -----------------------------------------------------------------------------


class HyCoCLIPProvider(BaseEmbeddingProvider):
    """Clean HyCoCLIP provider (PyTorch) - no hycoclip package dependency.

    Requires: torch, torchvision, timm (install via `uv sync --extra ml`)
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._model_spec: ModelSpec | None = None
        self._device: Any = None
        self._transform: Any = None

    @property
    def provider_id(self) -> str:
        return "hycoclip"

    def _get_device(self) -> Any:
        import torch

        if self._device is None:
            self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return self._device

    def _get_transform(self) -> Any:
        if self._transform is None:
            from torchvision import transforms

            self._transform = transforms.Compose([
                transforms.Resize(224, transforms.InterpolationMode.BICUBIC),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.48145466, 0.4578275, 0.40821073],
                    std=[0.26862954, 0.26130258, 0.27577711],
                ),
            ])
        return self._transform

    def _resolve_checkpoint(self, checkpoint: str) -> Path:
        """Resolve checkpoint path, downloading from HuggingFace if needed."""
        # Handle HuggingFace Hub URLs: hf://repo_id#filename
        if checkpoint.startswith("hf://"):
            try:
                from huggingface_hub import hf_hub_download
            except ImportError as exc:
                raise ImportError(
                    "hf:// checkpoints require huggingface_hub. "
                    "Install with: uv add huggingface-hub"
                ) from exc

            path = checkpoint[5:]
            if "#" not in path:
                raise ValueError(f"HF checkpoint must include filename: {checkpoint}")
            repo_id, filename = path.split("#", 1)
            return Path(hf_hub_download(repo_id=repo_id, filename=filename)).resolve()

        # Local path
        path = Path(checkpoint).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {path}")
        return path

    def _load_model(self, model_spec: ModelSpec) -> None:
        if self._model is not None and self._model_spec == model_spec:
            return

        # Auto-resolve checkpoint from model_id if not provided
        checkpoint = model_spec.checkpoint
        if not checkpoint:
            checkpoint = HYCOCLIP_CHECKPOINTS.get(model_spec.model_id)
            if not checkpoint:
                available = ", ".join(sorted(HYCOCLIP_CHECKPOINTS.keys()))
                raise ValueError(
                    f"Unknown HyCoCLIP model_id: '{model_spec.model_id}'. "
                    f"Known models: {available}. "
                    f"Or provide 'checkpoint' path explicitly."
                )

        checkpoint_path = self._resolve_checkpoint(checkpoint)
        self._model = _load_encoder(str(checkpoint_path), str(self._get_device()))
        self._model_spec = model_spec

    def compute_embeddings(
        self,
        samples: list["Sample"],
        model_spec: ModelSpec,
        batch_size: int = 32,
        show_progress: bool = True,
    ) -> np.ndarray:
        """Compute hyperboloid embeddings for samples."""
        import torch

        self._load_model(model_spec)
        assert self._model is not None

        device = self._get_device()
        transform = self._get_transform()

        if show_progress:
            print(f"Computing HyCoCLIP embeddings for {len(samples)} samples...")

        all_embeddings = []

        for i in range(0, len(samples), batch_size):
            batch_samples = samples[i : i + batch_size]

            images = []
            for sample in batch_samples:
                img = sample.load_image()
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(transform(img))

            batch_tensor = torch.stack(images).to(device)

            with torch.no_grad(), torch.amp.autocast(
                device_type=device.type, enabled=device.type == "cuda"
            ):
                embeddings = self._model(batch_tensor)

            all_embeddings.append(embeddings.cpu().numpy())

        return np.concatenate(all_embeddings, axis=0)

    def get_space_config(self, model_spec: ModelSpec, dim: int) -> dict[str, Any]:
        """Return embedding space configuration with curvature."""
        self._load_model(model_spec)
        assert self._model is not None

        return {
            "provider": self.provider_id,
            "model_id": model_spec.model_id,
            "geometry": "hyperboloid",
            "checkpoint": model_spec.checkpoint,
            "dim": dim,
            "curvature": self._model.curvature,
            "spatial_dim": self._model.embed_dim,
        }


# Auto-register on import
register_provider("hycoclip", HyCoCLIPProvider)
