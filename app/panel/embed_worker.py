"""The embedding model in its own process (started by docembed.py with python -I, never by hand).

Reads one JSON line per request from stdin: {"kind": "query" | "passage", "texts": [...]}, writes one
JSON line per answer: {"vecs": base64 of float16 values, DIM per text, length 1} or {"error": "..."}.
The first line it writes says whether it is ready, with the SHA-256 of the model files.
"""
import base64
import hashlib
import json
import os
import sys

REPO = "Xenova/multilingual-e5-small"     # intfloat/multilingual-e5-small as quantized ONNX
FILES = ("onnx/model_quantized.onnx", "tokenizer.json")
MAX_TOKENS = 512
MAX_TEXTS = 16


def say(d):
    sys.stdout.write(json.dumps(d) + "\n")
    sys.stdout.flush()


def main():
    try:
        os.nice(10)      # background work: the panel, speech and the language model go first
    except OSError:
        pass
    try:
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        paths = {f: hf_hub_download(REPO, f) for f in FILES}
        sha = {}
        for f, p in paths.items():
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for block in iter(lambda: fh.read(1 << 20), b""):
                    h.update(block)
            sha[f] = h.hexdigest()
        tok = Tokenizer.from_file(paths["tokenizer.json"])
        tok.enable_truncation(MAX_TOKENS)
        tok.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.inter_op_num_threads = 1
        sess = ort.InferenceSession(paths["onnx/model_quantized.onnx"], opts, providers=["CPUExecutionProvider"])
        names = {i.name for i in sess.get_inputs()}
    except Exception as e:
        say({"ready": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return
    say({"ready": True, "sha": sha})
    for line in sys.stdin:
        try:
            req = json.loads(line)
            prefix = "query: " if req.get("kind") == "query" else "passage: "
            texts = [prefix + str(t)[:2000] for t in req["texts"][:MAX_TEXTS]]
            enc = tok.encode_batch(texts)
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in names:
                feeds["token_type_ids"] = np.zeros_like(ids)
            out = sess.run(None, feeds)[0]                      # (texts, tokens, 384)
            m = mask[:, :, None].astype(np.float32)
            v = (out * m).sum(1) / np.maximum(m.sum(1), 1e-9)   # mean over the real tokens
            v /= np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
            say({"vecs": base64.b64encode(v.astype(np.float16).tobytes()).decode()})
        except Exception as e:
            say({"error": f"{type(e).__name__}: {str(e)[:200]}"})


if __name__ == "__main__":
    main()
