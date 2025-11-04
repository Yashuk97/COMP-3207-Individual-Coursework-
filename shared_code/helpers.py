import os
import json
import logging
import requests
from azure.cosmos import exceptions
import azure.functions as func

# Generic JSON response
def _ok(payload, code=200):
    """Return JSON HttpResponse with given payload and status."""
    return func.HttpResponse(json.dumps(payload, default=str),
                             mimetype="application/json", status_code=code)

# Request body parsing
def _get_body(req: func.HttpRequest) -> dict:
    """Parse body or query parameters from HttpRequest."""
    try:
        return req.get_json()
    except ValueError:
        pass
    j = req.params.get("json")
    if j:
        try:
            return json.loads(j)
        except Exception:
            pass
    players = req.params.get("players")
    tags = req.params.get("tag_list")
    body = {}
    if players:
        body["players"] = players.split(",")
    if tags:
        body["tag_list"] = tags.split(",")
    return body

# Cosmos helper
def _player_by_username(username: str):
    """Return player document by username, or None if not found."""
    from function_app import PLAYER_C  # local import to avoid circular import

    try:
        player = PLAYER_C.read_item(item=username, partition_key=username)
        return player
    except exceptions.CosmosResourceNotFoundError:
        q = "SELECT * FROM c WHERE c.username = @u"
        res = list(PLAYER_C.query_items(
            q,
            parameters=[{"name": "@u", "value": username}],
            enable_cross_partition_query=True
        ))
        return res[0] if res else None
    except Exception as e:
        logging.error(f"Error in _player_by_username: {e}")
        return None

    
# Translator helpers
def _translator_base():
    base = os.getenv("TranslationEndpoint", "").strip()
    if not base.startswith("http"):
        base = "https://" + base
    if not base.endswith("/"):
        base += "/"
    return base

def _translator_headers():
    return {
        "Ocp-Apim-Subscription-Key": os.getenv("TranslationKey"),
        "Ocp-Apim-Subscription-Region": os.getenv("TRANSLATOR_REGION", "francecentral"),
        "Content-Type": "application/json"
    }

def _translate_detect(text: str):
    base = _translator_base()
    headers = _translator_headers()
    url = f"{base}translate?api-version=3.0&to=en"
    try:
        resp = requests.post(url, headers=headers, json=[{"text": text}], timeout=10)
        resp.raise_for_status()
        data = resp.json()[0]
        det = data.get("detectedLanguage", {}) or {}
        return det.get("language", ""), float(det.get("score", 0.0))
    except Exception as e:
        logging.error(f"Translate detect error: {e}")
        return "", 0.0

def _translate_to_all(text: str):
    from function_app import SUPPORTED_CODES  # local import to avoid circular import
    base = _translator_base()
    headers = _translator_headers()
    lang, _score = _translate_detect(text)
    if not lang:
        lang = "en"

    targets = [code for code in SUPPORTED_CODES if code != lang]
    texts = [{"language": lang, "text": text}]

    if targets:
        to_params = "&".join([f"to={t}" for t in targets])
        url = f"{base}translate?api-version=3.0&{to_params}"
        try:
            resp = requests.post(url, headers=headers, json=[{"text": text}], timeout=15)
            resp.raise_for_status()
            for t in resp.json()[0].get("translations", []):
                to_code = t.get("to")
                txt = t.get("text", "")
                if to_code in targets:
                    texts.append({"language": to_code, "text": txt})
        except Exception as e:
            logging.error(f"Batch translate error: {e}")

    have = {x["language"] for x in texts}
    missing = [c for c in SUPPORTED_CODES if c not in have]
    for m in missing:
        try:
            r2 = requests.post(f"{base}translate?api-version=3.0&to={m}", headers=headers,
                               json=[{"text": text}], timeout=10)
            if r2.ok:
                t2 = r2.json()[0]["translations"][0]["text"]
                texts.append({"language": m, "text": t2})
        except Exception as e:
            logging.error(f"Fallback translate error for {m}: {e}")
    return texts


# Content Safety helper
def _content_safety_average_english(texts: list[dict]):
    """Compute average severity for English text."""
    en = next((t["text"] for t in texts if t["language"] == "en"), "")
    base = os.getenv("CONTENT_SAFETY_ENDPOINT", "").strip()
    if not base.startswith("http"):
        base = "https://" + base
    if not base.endswith("/"):
        base += "/"
    url = f"{base}contentsafety/text:analyze?api-version=2023-10-01"
    headers = {
        "Ocp-Apim-Subscription-Key": os.getenv("CONTENT_SAFETY_KEY"),
        "Content-Type": "application/json"
    }
    payload = {
        "text": en,
        "categories": ["Hate", "SelfHarm", "Sexual", "Violence"],
        "haltOnBlocklistHit": False
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logging.error(f"Content Safety error: {e}")
        return 0.0

    severities = []
    for cat in ["Hate", "SelfHarm", "Sexual", "Violence"]:
        for item in data.get("categoriesAnalysis", []):
            if item.get("category") == cat:
                severities.append(float(item.get("severity", 0.0)))
                break
    return sum(severities) / 4.0 if severities else 0.0

