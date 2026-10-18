"""Bilder malen: the image service (plan plaene/bildgenerierung.md, Dominik 2026-10-14). Unit speech-spark-bild,
only on 127.0.0.1 (image.port, 31005); the panel is its only caller (bilder.py).

The engine is stable-diffusion.cpp's sd-server with FLUX.2 [klein] (bildmodell.py: files, variant, memory). It runs
only on demand (Dominik 3a): the first picture starts it as a child process on 127.0.0.1 (image.engine_port, 31015),
image.idle_min minutes without a picture stop it again, so it holds no memory while nobody paints. Before it starts,
common.check_memory looks at the unified memory with the variant's need; too little is a 503 "memory", never a start
that pushes DGX OS into killing. One picture at a time. The unit's OOMScoreAdjust (1000) makes the engine the first
thing to go when memory runs out anyway, before the speech services and the panel.

Every picture is checked here (Dominik 5a): a small classifier (bildmodell.CHECKER, CPU) gives the share for
nudity, which the panel compares with its fixed threshold; then Pillow encodes the picture again (nothing of the
engine's file survives, no prompt in the metadata) and marks it as made by an AI (PNG text and the IPTC
"trainedAlgorithmicMedia" source type in XMP). The service never logs a prompt: only sizes, seconds and states.

    GET  /health        status (off | starting | ready | busy | error | missing), variant, counts, measurements
    POST /v1/bild       {prompt, width, height, seed?, refs?: [base64 PNG/JPEG]} -> {png, seconds, nsfw, seed, w, h}
    POST /v1/bild/stop  ends the engine now (Wartungspause, Bild testen)
"""
import asyncio
import base64
import io
import os
import time

import httpx
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request

import bildmodell
from bedarf import Belegt, OnDemand, idle_loop
from common import BodyLimit, api_key_dependency, api_key_ok, check_memory, load_config, mem_available_gib, quiet_access_log

MAX_BODY = 16 * 1024**2
MAX_PROMPT = 2000
MAX_REFS = 2
MAX_PIXELS = 2_100_000        # hard bound of the service; the panel's own limit is smaller (image.max_side)
MIN_SIDE, MAX_SIDE = 256, 2048
MAX_PNG = 40 * 1024**2        # what the engine hands back, before decoding
START_S = 300                 # the engine loads the models (first start after boot reads them from disk)
JOB_S = 300                   # one picture
POLL_S = 0.3
AI_TEXT = "KI-erzeugt mit FLUX.2 [klein] auf dem Spark / AI-generated with FLUX.2 [klein] on the Spark"
# Bilder ändern (a picture with a reference): marked as changed by an AI, IPTC "composite with trained algorithmic media"
AI_TEXT_EDIT = "KI-bearbeitet mit FLUX.2 [klein] auf dem Spark / AI-edited with FLUX.2 [klein] on the Spark"
XMP = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
       '<rdf:Description xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
       'Iptc4xmpExt:DigitalSourceType="http://cv.iptc.org/newscodes/digitalsourcetype/{kind}"/>'
       '</rdf:RDF></x:xmpmeta>')

app = FastAPI(title="Bilder malen (FLUX.2 klein via stable-diffusion.cpp)")
app.add_middleware(BodyLimit, default=MAX_BODY, gate=api_key_ok, gated=("/v1/",))
auth = [Depends(api_key_dependency())]
started = time.time()
stats = {"pictures": 0, "failures": 0, "refused_memory": 0, "refused_place": 0, "starts": 0, "last_s": None, "load_s": None,
         "engine_gib": None, "peak_gib": None}


def cfg():
    return load_config("image")


class Engine(OnDemand):
    """sd-server as a child process: started on demand, ended after image.idle_min minutes without a picture."""

    def __init__(self):
        super().__init__("bild")

    @property
    def base(self):
        return f"http://127.0.0.1:{int(cfg()['engine_port'])}"

    def command(self):
        c = cfg()
        v = bildmodell.variant(c.get("variant"))
        m = bildmodell.VARIANTS[v]
        return [bildmodell.ENGINE, "--diffusion-model", bildmodell.path(m["model"]), "--vae", bildmodell.path(bildmodell.VAE),
                "--llm", bildmodell.path(m["llm"]), "--listen-ip", "127.0.0.1", "--listen-port", str(int(c["engine_port"])),
                "--cfg-scale", str(bildmodell.GUIDANCE), "--steps", str(bildmodell.STEPS), "--log-level", "error"]

    async def start(self):
        if self.alive() and self.state == "ready":
            return
        v = bildmodell.variant(cfg().get("variant"))
        if not bildmodell.installed(v):
            self.state = "error"
            raise HTTPException(503, "missing")
        try:   # one model on demand at a time (bedarf.py): the place first, then the memory
            self.claim()
        except Belegt:
            stats["refused_place"] += 1
            raise HTTPException(503, "belegt")
        try:
            check_memory(bildmodell.VARIANTS[v]["need_gib"])
        except MemoryError:
            self.release()
            stats["refused_memory"] += 1
            print(f"bild: engine nicht gestartet speicher {mem_available_gib():.1f} gib frei", flush=True)
            raise HTTPException(503, "memory")
        before = mem_available_gib()
        t0 = time.time()
        self.state = "starting"
        stats["starts"] += 1
        self.spawn(self.command(), bildmodell.FOLDER)
        while time.time() - t0 < START_S:
            if not self.alive():
                self.state = "error"
                print(f"bild: engine beendet beim start code {self.proc.returncode}", flush=True)
                self.stop("fehler")
                raise HTTPException(503, "engine")
            try:
                r = await self.client.get(self.base + "/sdcpp/v1/capabilities")
                if r.status_code == 200:
                    self.state = "ready"
                    self.used = time.time()
                    stats["load_s"] = round(time.time() - t0, 1)
                    stats["engine_gib"] = round(max(0.0, before - mem_available_gib()), 1)
                    print(f"bild: engine gestartet {stats['load_s']} s {stats['engine_gib']} gib", flush=True)
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        self.stop("zeitlimit")
        self.state = "error"
        raise HTTPException(503, "engine")

    async def paint(self, body):
        """One picture: (PNG bytes from the engine, seconds, GiB the picture took on top of the loaded engine)."""
        async with self.lock:
            await self.start()
            self.busy = True
            t0 = time.time()
            first = low = mem_available_gib()
            try:
                r = await self.client.post(self.base + "/sdcpp/v1/img_gen", json=body)
                if r.status_code != 202:
                    raise HTTPException(502, "engine")
                job = str(r.json().get("id") or "")
                if not job or not job.replace("_", "").isalnum():
                    raise HTTPException(502, "engine")
                while time.time() - t0 < JOB_S:
                    await asyncio.sleep(POLL_S)
                    low = min(low, mem_available_gib())
                    if not self.alive():
                        self.state = "error"
                        raise HTTPException(502, "engine")
                    j = (await self.client.get(f"{self.base}/sdcpp/v1/jobs/{job}")).json()
                    if j.get("status") == "completed":
                        img = ((j.get("result") or {}).get("images") or [{}])[0].get("b64_json") or ""
                        if not img or len(img) > MAX_PNG * 4 // 3 + 4:
                            raise HTTPException(502, "engine")
                        return base64.b64decode(img), time.time() - t0, max(0.0, first - low)
                    if j.get("status") in ("failed", "cancelled"):
                        raise HTTPException(502, "engine")
                try:
                    await self.client.post(f"{self.base}/sdcpp/v1/jobs/{job}/cancel")
                except httpx.HTTPError:
                    pass
                raise HTTPException(504, "timeout")
            except httpx.HTTPError:
                raise HTTPException(502, "engine")
            finally:
                self.busy = False
                self.used = time.time()


engine = Engine()
_checker = []


def nsfw_share(im):
    """The classifier's share for "nsfw" (0..1) for a Pillow image, or None when the checker is missing."""
    import numpy as np
    if not _checker:
        p = bildmodell.path(bildmodell.CHECKER)
        if not os.path.isfile(p):
            return None
        import onnxruntime
        so = onnxruntime.SessionOptions()
        so.intra_op_num_threads = 2
        _checker.append(onnxruntime.InferenceSession(p, sess_options=so, providers=["CPUExecutionProvider"]))
    s = _checker[0]
    side = bildmodell.CHECK_SIDE
    x = np.asarray(im.convert("RGB").resize((side, side)), dtype=np.float32) / 255.0
    x = ((x - 0.5) / 0.5).transpose(2, 0, 1)[None]
    logits = s.run(None, {s.get_inputs()[0].name: x})[0][0]
    e = np.exp(logits - logits.max())
    return float((e / e.sum())[1])   # labels: 0 sfw, 1 nsfw


def finish(raw, edited=False):
    """The engine's picture -> (our own PNG with the AI marks, width, height, nsfw share). Raises ValueError for
    anything that is not a picture of a sane size. edited: made from a reference picture (Bilder ändern)."""
    from PIL import Image, PngImagePlugin
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format != "PNG" or im.width * im.height > MAX_PIXELS * 2:
            raise ValueError("no picture")
        im.load()
    except (OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("no picture")
    im = im.convert("RGB")
    share = nsfw_share(im)
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Software", "Speech on DGX Spark")
    meta.add_text("Comment", AI_TEXT_EDIT if edited else AI_TEXT)
    meta.add_itxt("XML:com.adobe.xmp", XMP.format(kind="compositeWithTrainedAlgorithmicMedia" if edited
                                                  else "trainedAlgorithmicMedia"))
    out = io.BytesIO()
    im.save(out, "PNG", pnginfo=meta, optimize=True)
    return out.getvalue(), im.width, im.height, share


def side(v, name):
    if isinstance(v, bool) or not isinstance(v, int) or not MIN_SIDE <= v <= MAX_SIDE or v % 16:
        raise HTTPException(400, f"{name}: {MIN_SIDE}-{MAX_SIDE}, a multiple of 16")
    return v


def ref_image(b64):
    """A reference picture (Bild ändern): decoded, at most 2 MP, again as a clean PNG in base64."""
    from PIL import Image
    try:
        raw = base64.b64decode(str(b64), validate=True)
        if len(raw) > 12 * 1024**2:
            raise ValueError
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS * 2
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("PNG", "JPEG", "WEBP") or im.width * im.height > MAX_PIXELS * 2:
            raise ValueError
        im.load()
        im = im.convert("RGB")
        im.thumbnail((1536, 1536))
        out = io.BytesIO()
        im.save(out, "PNG")
        return base64.b64encode(out.getvalue()).decode()
    except Exception:
        raise HTTPException(400, "refs: a PNG, JPEG or WebP picture")


def request_body(b):
    if not isinstance(b, dict):
        raise HTTPException(400, "JSON object")
    prompt = b.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT:
        raise HTTPException(400, f"prompt: 1-{MAX_PROMPT} characters")
    # sd-server reads nothing out of the native prompt, but angle brackets are never needed for a picture
    prompt = "".join(ch for ch in prompt if ch.isprintable() and ch not in "<>")
    w, h = side(b.get("width"), "width"), side(b.get("height"), "height")
    if w * h > MAX_PIXELS:
        raise HTTPException(400, "too many pixels")
    seed = b.get("seed", -1)
    if isinstance(seed, bool) or not isinstance(seed, int) or not -1 <= seed < 2**31:
        raise HTTPException(400, "seed")
    refs = b.get("refs") or []
    if not isinstance(refs, list) or len(refs) > MAX_REFS:
        raise HTTPException(400, f"refs: at most {MAX_REFS}")
    # every field fixed here: steps, sampler, guidance and the output never come from the caller
    return {"prompt": prompt, "negative_prompt": "", "width": w, "height": h, "seed": seed, "batch_count": 1,
            "ref_images": [ref_image(r) for r in refs], "embed_image_metadata": False, "preview": "none",
            "sample_params": {"sample_method": "euler", "sample_steps": bildmodell.STEPS,
                              "guidance": {"txt_cfg": bildmodell.GUIDANCE}},
            "output_format": "png", "output_compression": 100}


@app.post("/v1/bild", dependencies=auth)
async def bild(request: Request):
    try:
        body = request_body(await request.json())
    except ValueError:
        raise HTTPException(400, "JSON object")
    try:
        raw, secs, extra = await engine.paint(body)
        png, w, h, share = await asyncio.to_thread(finish, raw, bool(body["ref_images"]))
    except HTTPException as e:
        stats["failures"] += 1
        print(f"bild: nicht gemalt {e.detail}", flush=True)
        raise
    except ValueError:
        stats["failures"] += 1
        print("bild: nicht gemalt kein bild", flush=True)
        raise HTTPException(502, "engine")
    stats["pictures"] += 1
    stats["last_s"] = round(secs, 1)
    stats["peak_gib"] = round((stats["engine_gib"] or 0) + extra, 1)
    print(f"bild: gemalt {w}x{h} {bildmodell.STEPS} schritte {secs:.1f} s", flush=True)
    return {"png": base64.b64encode(png).decode(), "seconds": round(secs, 1), "nsfw": share, "w": w, "h": h,
            "seed": body["seed"], "refs": len(body["ref_images"])}


@app.post("/v1/bild/stop", dependencies=auth)
async def stop():
    async with engine.lock:
        engine.stop("auf wunsch")
    return {"ok": True}


@app.get("/health")
async def health(request: Request):
    c = cfg()
    v = bildmodell.variant(c.get("variant"))
    status = "missing" if not bildmodell.installed(v) else "busy" if engine.busy else engine.state
    out = {"service": "bild", "status": status, "variant": v, "name": bildmodell.VARIANTS[v]["name"],
           "license": bildmodell.VARIANTS[v]["license"], "need_gib": bildmodell.VARIANTS[v]["need_gib"],
           "idle_min": int(c["idle_min"]), "uptime_s": round(time.time() - started),
           "idle_s": round(time.time() - engine.used) if engine.state == "ready" else None, **stats}
    if not api_key_ok(request.scope):
        return {"service": "bild", "status": status}
    return out


@app.on_event("startup")
async def idle_stop():
    idle_loop(engine, lambda: cfg()["idle_min"])


@app.on_event("shutdown")
def end():
    engine.stop("dienst endet")


if __name__ == "__main__":
    quiet_access_log()
    c = cfg()
    uvicorn.run(app, host="127.0.0.1", port=int(c["port"]))
