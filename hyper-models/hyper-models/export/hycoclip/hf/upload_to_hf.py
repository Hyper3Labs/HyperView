"""Upload exported ONNX artifacts to the Hugging Face Hub.

Uploads ONNX models to a unified hyperbolic-clip repository with multiple
model variants organized in subdirectories.

Example:

    cd hyper_models/hycoclip_onnx
    uv run python hf/upload_to_hf.py \
        --repo-id mnm-matin/hyperbolic-clip \
        --model hycoclip-vit-s \
        --onnx ./outputs/hycoclip_vit_s_image_encoder.onnx \
        --onnx-data ./outputs/hycoclip_vit_s_image_encoder.onnx.data

Requirements:
- huggingface_hub: uv add huggingface-hub
- Login: hf auth login

Repository structure on HuggingFace:
    hyperbolic-clip/
    ├── README.md                    # Main repo card
    ├── hycoclip-vit-s/
    │   ├── model.onnx
    │   └── model.onnx.data
    ├── hycoclip-vit-b/
    │   └── ...
    └── meru-vit-s/
        └── ...

Important:
- HyCoCLIP/MERU is CC-BY-NC (non-commercial). Respect upstream licensing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Main repo README (shown on the HF repo page)
# ---------------------------------------------------------------------------
REPO_README_TEMPLATE = '''---
library_name: onnx
pipeline_tag: feature-extraction
license: cc-by-nc-4.0
tags:
  - onnx
  - vision
  - clip
  - hyperbolic
  - image-embedding
  - hyperboloid
  - non-euclidean
  - lorentz
  - meru
  - hycoclip
language:
  - en
---

# Hyperbolic CLIP Models (ONNX)

This repository contains **ONNX exports** of hyperbolic vision-language models for **hyperbolic image embeddings**.

## Available Models

| Model | Architecture | Embedding Dim | Size | Path |
|-------|--------------|---------------|------|------|
{model_table}

## Quick Start

```python
import onnxruntime as ort
import numpy as np
from huggingface_hub import hf_hub_download

# Download a model
onnx_path = hf_hub_download(
    repo_id="{repo_id}",
    filename="hycoclip-vit-s/model.onnx"  # or other model path
)

# Load and run
session = ort.InferenceSession(onnx_path)
image = np.random.rand(1, 3, 224, 224).astype(np.float32)  # Your preprocessed image
embedding, curvature = session.run(None, {{"image": image}})

print(f"Embedding shape: {{embedding.shape}}")  # (1, 513) - hyperboloid format
```

## Model Details

All models output embeddings in **Lorentz/Hyperboloid format**:
- Output: `(t, x₁...xₙ)` where `t = √(1/c + ‖x‖²)`
- Embedding dim: 513 (1 time component + 512 spatial)
- Curvature `c` is learned and exported as secondary output

### Converting to Poincaré Ball

```python
t = embedding[:, 0:1]   # time component
x = embedding[:, 1:]    # spatial components
poincare = x / (t + 1)  # stereographic projection
```

## Usage with HyperView

```python
import hyperview as hv
from huggingface_hub import hf_hub_download

# Download model
model_path = hf_hub_download("{repo_id}", "hycoclip-vit-s/model.onnx")

# Use with HyperView
ds = hv.Dataset("my_images")
ds.add_images_dir("/path/to/images")
ds.compute_embeddings(onnx_path=model_path)
hv.show(ds)
```

## License

**CC-BY-NC-4.0** (Non-commercial use only)

Based on:
- [PalAvik/hycoclip](https://github.com/PalAvik/hycoclip)
- [facebookresearch/meru](https://github.com/facebookresearch/meru)

## Citation

```bibtex
@inproceedings{{desai2023hyperbolic,
  title={{Hyperbolic Image-Text Representations}},
  author={{Desai, Karan and Nickel, Maximilian and Rajpurohit, Tanmay and Johnson, Justin and Vedantam, Ramakrishna}},
  booktitle={{ICML}},
  year={{2023}}
}}
```
'''

# Model-specific info for the table
MODEL_INFO = {
    "hycoclip-vit-s": {"arch": "ViT-S/16", "dim": 513, "size": "~84 MB"},
    "hycoclip-vit-b": {"arch": "ViT-B/16", "dim": 513, "size": "~350 MB"},
    "meru-vit-s": {"arch": "ViT-S/16", "dim": 513, "size": "~84 MB"},
    "meru-vit-b": {"arch": "ViT-B/16", "dim": 513, "size": "~350 MB"},
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Upload ONNX model to unified hyperbolic-clip repo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Repository structure:
  hyperbolic-clip/
  ├── README.md              # Auto-generated repo card
  ├── hycoclip-vit-s/
  │   ├── model.onnx
  │   └── model.onnx.data
  └── meru-vit-b/
      └── ...

Example:
  uv run python hf/upload_to_hf.py \\
      --repo-id mnm-matin/hyperbolic-clip \\
      --model hycoclip-vit-s \\
      --onnx ./outputs/hycoclip_vit_s_image_encoder.onnx \\
      --onnx-data ./outputs/hycoclip_vit_s_image_encoder.onnx.data
        """,
    )
    p.add_argument("--repo-id", required=True, help="HF repo (e.g. mnm-matin/hyperbolic-clip)")
    p.add_argument("--model", required=True, help="Model name/subfolder (e.g. hycoclip-vit-s, meru-vit-b)")
    p.add_argument("--onnx", required=True, help="Path to .onnx file")
    p.add_argument("--onnx-data", default=None, help="Path to .onnx.data file (external weights)")
    p.add_argument("--private", action="store_true", help="Create repo as private")
    p.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    return p.parse_args()


def _get_existing_models(api, repo_id: str) -> list[str]:
    """Get list of model subdirectories already in the repo."""
    try:
        files = list(api.list_repo_tree(repo_id, recursive=False))
        return [f.path for f in files if f.path not in ("README.md", ".gitattributes") and not f.path.startswith(".")]
    except Exception:
        return []


def _generate_model_table(models: list[str], repo_id: str) -> str:
    """Generate markdown table of available models."""
    if not models:
        return "| *No models uploaded yet* | | | | |"
    
    rows = []
    for model in sorted(models):
        info = MODEL_INFO.get(model, {"arch": "ViT", "dim": 513, "size": "~100 MB"})
        rows.append(f"| **{model}** | {info['arch']} | {info['dim']} | {info['size']} | `{model}/model.onnx` |")
    return "\n".join(rows)


def main() -> int:
    args = _parse_args()

    # Validate paths
    onnx_path = Path(args.onnx).expanduser().resolve()
    if not onnx_path.exists():
        raise SystemExit(f"ONNX file not found: {onnx_path}")
    if onnx_path.suffix.lower() != ".onnx":
        raise SystemExit(f"Expected .onnx file, got: {onnx_path}")

    data_path: Path | None = None
    if args.onnx_data:
        data_path = Path(args.onnx_data).expanduser().resolve()
        if not data_path.exists():
            raise SystemExit(f"ONNX data file not found: {data_path}")

    model_name = args.model.strip().lower()
    
    # Show what will be uploaded
    print("=" * 60)
    print("Hugging Face Upload Summary")
    print("=" * 60)
    print(f"Repository:  https://huggingface.co/{args.repo_id}")
    print(f"Model:       {model_name}")
    print(f"Private:     {args.private}")
    print()
    print("Files to upload:")
    print(f"  - {model_name}/model.onnx ({onnx_path.stat().st_size / 1024 / 1024:.2f} MB)")
    if data_path:
        print(f"  - {model_name}/model.onnx.data ({data_path.stat().st_size / 1024 / 1024:.2f} MB)")
    print(f"  - README.md (repo card, will be updated)")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN] Would upload the above files.")
        return 0

    # Import huggingface_hub and onnx
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: huggingface_hub\n"
            "Install with: uv add huggingface-hub\n"
            "Then login with: hf auth login"
        ) from exc

    try:
        import onnx
        from onnx.external_data_helper import convert_model_to_external_data
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency: onnx\n"
            "Install with: uv add onnx"
        ) from exc

    api = HfApi()

    # Create repo if needed
    print("\nCreating repository (if needed)...")
    api.create_repo(repo_id=args.repo_id, private=args.private, exist_ok=True)

    # Rewrite external data location to match the uploaded filename (model.onnx.data)
    # This is necessary because the original export may have used a different filename.
    print("Rewriting ONNX external data location to 'model.onnx.data'...")
    import tempfile
    onnx_model = onnx.load(str(onnx_path), load_external_data=True)
    convert_model_to_external_data(
        onnx_model,
        all_tensors_to_one_file=True,
        location="model.onnx.data",
        size_threshold=1024,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_onnx = Path(tmpdir) / "model.onnx"
        onnx.save_model(onnx_model, str(tmp_onnx))
        tmp_data = Path(tmpdir) / "model.onnx.data"

        # Upload rewritten ONNX file
        print(f"Uploading {model_name}/model.onnx...")
        api.upload_file(
            repo_id=args.repo_id,
            path_or_fileobj=str(tmp_onnx),
            path_in_repo=f"{model_name}/model.onnx",
            commit_message=f"Add {model_name} ONNX model",
        )

        # Upload the rewritten external data file
        if tmp_data.exists():
            print(f"Uploading {model_name}/model.onnx.data...")
            api.upload_file(
                repo_id=args.repo_id,
                path_or_fileobj=str(tmp_data),
                path_in_repo=f"{model_name}/model.onnx.data",
                commit_message=f"Add {model_name} ONNX weights",
            )

    # Update repo README with model table
    print("Updating README.md...")
    existing_models = _get_existing_models(api, args.repo_id)
    if model_name not in existing_models:
        existing_models.append(model_name)
    
    model_table = _generate_model_table(existing_models, args.repo_id)
    readme_content = REPO_README_TEMPLATE.format(
        repo_id=args.repo_id,
        model_table=model_table,
    )
    
    api.upload_file(
        repo_id=args.repo_id,
        path_or_fileobj=readme_content.encode("utf-8"),
        path_in_repo="README.md",
        commit_message=f"Update README with {model_name}",
    )

    print()
    print("✅ Successfully uploaded to Hugging Face!")
    print(f"   https://huggingface.co/{args.repo_id}")
    print(f"   Model path: {model_name}/model.onnx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
