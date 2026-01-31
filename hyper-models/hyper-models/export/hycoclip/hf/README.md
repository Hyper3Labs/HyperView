# Hugging Face Hub publishing (template)

This folder is a lightweight starting point for publishing HyCoCLIP/MERU ONNX artifacts to the Hugging Face Hub.

What you typically publish:
- `*.onnx`
- optional external data file `*.onnx.data` (must sit next to the `.onnx`)
- a short model card with licensing + attribution

Recommended repo layout:

```
README.md
onnx/
	image_encoder.onnx
	image_encoder.onnx.data
```

Consumption tip:
- Prefer `huggingface_hub.snapshot_download(...)` (not `hf_hub_download`) so you reliably fetch both `.onnx` and `.onnx.data`.

Notes:
- Upstream HyCoCLIP is CC-BY-NC; make sure you include the correct license/attribution and only publish if permitted.

Suggested repo naming (example):
- `your-org/hycoclip-vit-s-image-encoder-onnx`

See `upload_to_hf.py` for a minimal upload helper.
