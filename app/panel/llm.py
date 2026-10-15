"""One way to the language model (Große Aufräumaktion step 3, Richtlinie Teil 17): its address, key, model name and
the plain call. Background jobs ask with complete(); the turns that stream or carry tools (chat.py, agent.py) and the
checks (health.py, vorrang.py) take url(), headers() and model() from here, so the address of the model computer is
in this one place (plan Raspberry-Pi split, B1).

Everything the model answers is data, never a command (Richtlinie Teil 2): complete() returns plain text without the
thinking; the caller checks it with fixed rules.
"""
import httpx

from common import load_config, no_think

_models = {}   # address -> the model it serves (when chat.llm_model is not set)


def url(ccfg):
    """The chat/completions address of the configured model."""
    return str(ccfg["llm_url"]).rstrip("/") + "/chat/completions"


def own_tor(ccfg, cfg=None):
    """True when the address is this Spark's own LLM-Tor (llm_tor.py on 127.0.0.1:llm.port, plan eigene-modelle E3)."""
    import re
    cfg = load_config() if cfg is None else cfg
    port = (cfg.get("llm") or {}).get("port", 31006)
    m = re.match(r"^http://(127\.0\.0\.1|localhost):(\d+)(/|$)", str(ccfg.get("llm_url") or ""))
    return bool(m) and int(m.group(2)) == port


def key(ccfg, cfg=None):
    """The key for the model: chat.llm_key, else for the own LLM-Tor the speech API key (api.key), so a new API key
    (speech-spark key new, Einstellungen) never leaves the chat without its model."""
    if ccfg.get("llm_key"):
        return str(ccfg["llm_key"])
    cfg = load_config() if cfg is None else cfg
    return str((cfg.get("api") or {}).get("key") or "") if own_tor(ccfg, cfg) else ""


def headers(ccfg):
    k = key(ccfg)
    return {"Authorization": f"Bearer {k}"} if k else {}


async def model(c, ccfg, hdrs=None):
    """The model's name: the configured one, else the first the server lists (asked once per address)."""
    if ccfg.get("llm_model"):
        return ccfg["llm_model"]
    base = str(ccfg["llm_url"]).rstrip("/")
    if base not in _models:
        r = await c.get(base + "/models", headers=headers(ccfg) if hdrs is None else hdrs, timeout=10)
        r.raise_for_status()
        _models[base] = r.json()["data"][0]["id"]
    return _models[base]


def known_model():
    """The model name already asked for, without a request ("" before the first call)."""
    return next(iter(_models.values()), "")


def content(r):
    """The text of a finished answer, without the thinking."""
    return no_think(str(((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""))


async def post(c, ccfg, job, payload, who=None, speech_first=True):
    """One finished (not streamed) request with the payload as it is. speech_first: through vorrang (waits while
    speech runs, counted under job); else straight, counted under job as well (verbrauch.py)."""
    import verbrauch
    import vorrang
    if speech_first:
        return await vorrang.post(c, job, url(ccfg), who=who, json=payload, headers=headers(ccfg))
    r = await c.post(url(ccfg), json=payload, headers=headers(ccfg))
    verbrauch.response(job, r, payload, who)
    return r


async def complete(system, user, job, max_tokens, temperature=0.1, timeout=120, who=None, ccfg=None,
                   speech_first=True, thinking=False, messages=None, c=None, model_name=None, **extra):
    """The model's answer to one system prompt and one user text (or the given messages) as plain text without
    the thinking. Raises httpx.HTTPError (also on an error status) and ValueError/KeyError on a broken answer.
    thinking=None leaves the model's own default; model_name: a name already known (the turn's own), else asked;
    extra goes into the payload as it is (e.g. stream=False)."""
    ccfg = load_config("chat") if ccfg is None else ccfg
    msgs = messages if messages is not None else [{"role": "system", "content": system},
                                                   {"role": "user", "content": user}]

    async def ask(cl):
        payload = {"model": model_name or await model(cl, ccfg), "temperature": temperature, "max_tokens": max_tokens,
                   "messages": msgs}
        if thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": bool(thinking)}
        payload.update(extra)
        r = await post(cl, ccfg, job, payload, who=who, speech_first=speech_first)
        r.raise_for_status()
        return content(r)

    if c is not None:
        return await ask(c)
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=5)) as cl:
        return await ask(cl)
