"""The embedding model in its own process (started by docembed.py with python -I as `embed_worker.py embed REPO
COMMIT`, never by hand; repository and pinned commit from the model catalog, every file checked against it).

Reads one JSON line per request from stdin: {"kind": "query" | "passage", "texts": [...]}, writes one
JSON line per answer: {"vecs": base64 of float16 values, DIM per text, length 1} or {"error": "..."}.
The first line it writes says whether it is ready, with the SHA-256 of the model files and the commit they were
checked against.

Started as `embed_worker.py rank klein|gross REPO COMMIT` (nachsortieren.py) it holds a cross-encoder instead: requests
{"query": "...", "texts": [...]}, answers {"scores": [...]} (one raw score per text, higher fits better).
"""
import base64
import hashlib
import json
import os
import re
import sys

FILES = ("onnx/model_quantized.onnx", "tokenizer.json")     # the embedding model: multilingual-e5-small as quantized ONNX
MAX_TOKENS = 512
MAX_TEXTS = 16
# the re-ranking models (Stufe 3 of plan suche-schaerfen): size -> (ONNX file, most tokens). Repository and pinned
# commit come from the model catalog through the caller (docembed.py, nachsortieren.py: modelle.fest), never "main"
RANK = {"klein": ("onnx/model_qint8_arm64.onnx", 384), "gross": ("onnx/model_quantized.onnx", 512)}
REPO_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
REV_RE = re.compile(r"[0-9a-f]{40}")
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


def hole(repo, rev, f):
    """One file of the pinned commit, checked against its name in the cache (SHA-256 of a large file, git blob hash of
    a small one; like modelle.pruefen, which this process cannot import under python -I). Returns (path, SHA-256)."""
    from huggingface_hub import hf_hub_download
    p = hf_hub_download(repo, f, revision=rev)
    # the name to check is the model's own blob (blobs/<hash>, where the snapshot's link points); newer huggingface_hub
    # links that once more into the shared hub/blobs/<2 hex>/, whose file is not named by the hash (as in modelle.pruefen)
    blob, sha = (os.path.basename(os.readlink(p)) if os.path.islink(p) else ""), _sha(p)
    if re.fullmatch(r"[0-9a-f]{40}", blob):
        h = hashlib.sha1(b"blob %d\0" % os.path.getsize(p))
        with open(p, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        ok = h.hexdigest() == blob
    else:
        ok = sha == blob
    if not ok:
        raise RuntimeError(f"{f} does not match its commit")
    return p, sha


def rank_main(size, repo, rev):
    """The cross-encoder: question and passage read together, one score per passage."""
    try:
        os.nice(10)
    except OSError:
        pass
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        f, most = RANK[size]
        (model, sha_m), (tokfile, sha_t) = hole(repo, rev, f), hole(repo, rev, "tokenizer.json")
        sha = {f"{repo}/{f}": sha_m, f"{repo}/tokenizer.json": sha_t}
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
    say({"ready": True, "sha": sha, "commit": rev})   # the commit every file was checked against (hole)
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
    a = sys.argv[1:]
    if len(a) == 4 and a[0] == "rank" and a[1] in RANK and REPO_RE.fullmatch(a[2]) and REV_RE.fullmatch(a[3]):
        return rank_main(*a[1:])
    if not (len(a) == 3 and a[0] == "embed" and REPO_RE.fullmatch(a[1]) and REV_RE.fullmatch(a[2])):
        say({"ready": False, "error": "usage: embed_worker.py embed REPO COMMIT | rank klein|gross REPO COMMIT"})
        return
    repo, rev = a[1], a[2]
    try:
        os.nice(10)      # background work: the panel, speech and the language model go first
    except OSError:
        pass
    try:
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        got = {f: hole(repo, rev, f) for f in FILES}
        paths, sha = {f: p for f, (p, _) in got.items()}, {f: h for f, (_, h) in got.items()}
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
    say({"ready": True, "sha": sha, "commit": rev})   # the commit every file was checked against (hole)
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
