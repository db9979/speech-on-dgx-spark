"""The embedding model in its own process (started by docembed.py with python -I, never by hand).

Reads one JSON line per request from stdin: {"kind": "query" | "passage", "texts": [...]}, writes one
JSON line per answer: {"vecs": base64 of float16 values, DIM per text, length 1} or {"error": "..."}.
The first line it writes says whether it is ready, with the SHA-256 of the model files.

Started as `embed_worker.py rank klein|gross` (nachsortieren.py) it holds a cross-encoder instead: requests
{"query": "...", "texts": [...]}, answers {"scores": [...]} (one raw score per text, higher fits better).
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
# the re-ranking models (Stufe 3 of plan suche-schaerfen): (repository, ONNX file) tried in this order, the
# first that downloads is used; its SHA-256 is pinned the first time like the embedding model's
RANK = {"klein": ((("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "onnx/model_qint8_arm64.onnx"),
                   ("cross-encoder/mmarco-mMiniLMv2-L12-H384-v1", "onnx/model.onnx")), 384),
        "gross": ((("onnx-community/bge-reranker-v2-m3-ONNX", "onnx/model_quantized.onnx"),
                   ("BAAI/bge-reranker-v2-m3", "onnx/model.onnx")), 512)}
RANK_TEXTS = 40


def say(d):
    sys.stdout.write(json.dumps(d) + "\n")
    sys.stdout.flush()


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rank_main(size):
    """The cross-encoder: question and passage read together, one score per passage."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        tries, most = RANK[size]
        got, last = None, None
        for repo, f in tries:
            try:
                got = (repo, f, hf_hub_download(repo, f), hf_hub_download(repo, "tokenizer.json"))
                break
            except Exception as e:      # this file is not there (another build of the model): the next one
                last = e
        if not got:
            raise last or RuntimeError("no model file")
        repo, f, model, tokfile = got
        sha = {f"{repo}/{f}": _sha(model), f"{repo}/tokenizer.json": _sha(tokfile)}
        tok = Tokenizer.from_file(tokfile)
        tok.enable_truncation(most)
        tok.enable_padding()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 4
        opts.inter_op_num_threads = 1
        sess = ort.InferenceSession(model, opts, providers=["CPUExecutionProvider"])
        names = {i.name for i in sess.get_inputs()}
    except Exception as e:
        say({"ready": False, "error": f"{type(e).__name__}: {str(e)[:200]}"})
        return
    say({"ready": True, "sha": sha})
    for line in sys.stdin:
        try:
            req = json.loads(line)
            q = str(req["query"])[:500]
            enc = tok.encode_batch([(q, str(t)[:2000]) for t in req["texts"][:RANK_TEXTS]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            feeds = {"input_ids": ids, "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
            if "token_type_ids" in names:
                feeds["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
            out = np.asarray(sess.run(None, feeds)[0], dtype=np.float32).reshape(len(enc), -1)[:, -1]
            say({"scores": [round(float(x), 4) for x in out]})
        except Exception as e:
            say({"error": f"{type(e).__name__}: {str(e)[:200]}"})


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "rank" and sys.argv[2] in RANK:
        return rank_main(sys.argv[2])
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
