# This Azure Function App implements the Quiplash backend.
# It provides REST-style HTTP endpoints for:
#   - Player registration, login, and score updates
#   - Prompt creation, moderation, and deletion
#   - Utility endpoints for testing and data retrieval
# Data is stored in Azure Cosmos DB with two containers:
#   1. player (partition key: /username)
#   2. prompt (partition key: /username)

import logging
import json
import os
import uuid
import azure.functions as func
from azure.cosmos import CosmosClient, exceptions
from azure.functions import FunctionApp

from shared_code.helpers import (
    _ok,
    _get_body,
    _player_by_username,
    _translate_detect,
    _translate_to_all,
    _content_safety_average_english
)
# CONFIGURATION

# Environment variable set in Azure Portal
COSMOS = CosmosClient.from_connection_string(
    os.getenv("AzureCosmosDBConnectionString"))

# Database and container names
DB_NAME = "quiplash"
DB = COSMOS.get_database_client(DB_NAME)

PLAYER_C = DB.get_container_client("player")
PROMPT_C = DB.get_container_client("prompt")

# AZURE Translator (REST)
TranslationEndpoint = os.getenv("TranslationEndpoint", "").rstrip("/")
TranslationKey = os.getenv("TranslationKey")
TRANSLATOR_REGION = os.getenv("TRANSLATOR_REGION", "francecentral")

# Azure content safety (REST)
CS_ENDPOINT = os.getenv("ContentSafetyEndpoint", "").rstrip("/")
CS_KEY = os.getenv("ContentSafetyKey")


# Supported languages per spec
SUPPORTED_LANGS = [
    {"code": "en", "name": "English"},
    {"code": "cy", "name": "Welsh"},
    {"code": "es", "name": "Spanish"},
    {"code": "ta", "name": "Tamil"},
    {"code": "zh-Hans", "name": "Chinese (Simplified)"},
    {"code": "ar", "name": "Arabic"}

]
SUPPORTED_CODES = [l["code"] for l in SUPPORTED_LANGS]

# Auth level set to ANONYMOUS so routes are public
app = FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# ENDPOINT: /player/register(POST)
# register a new player with validation rules
@app.route(route="player/register", methods=["POST"])
@app.function_name(name="player_register")
def player_register(req: func.HttpRequest) -> func.HttpResponse:
    """Register a new player, enforcing length and uniqueness rules."""
    body = _get_body(req)
    username = body.get("username", "")
    password = body.get("password", "")

    if not (5 <= len(username) <= 12):
        return _ok({"result": False, "msg": "Username less than 5 characters or more than 12 characters"})
    if not (8 <= len(password) <= 12):
        return _ok({"result": False, "msg": "Password less than 8 characters or more than 12 characters"})

    if _player_by_username(username):
        return _ok({"result": False, "msg": "Username already exists"})

    doc = {
        "id": username,
        "username": username,
        "password": password,
        "games_played": 0,
        "total_score": 0
    }

    try:
        PLAYER_C.create_item(doc)
    except exceptions.CosmosResourceExistsError:
        return _ok({"result": False, "msg": "Username already exists"})
    except Exception as e:
        logging.error(f"Error creating player: {e}")
        return _ok({"result": False, "msg": "Internal error creating player"})

    return _ok({"result": True, "msg": "OK"})

# ENDPOINT: /player/login(GET)
# Validate player credentials

@app.route(route="player/login", methods=["GET"])
@app.function_name(name="player_login")
def player_login(req: func.HttpRequest) -> func.HttpResponse:
    # Support both query parameters and JSON body
    username = req.params.get("username") or ""
    password = req.params.get("password") or ""

    # Fallback to JSON body if provided
    if not username or not password:
        body = _get_body(req)
        username = username or body.get("username", "")
        password = password or body.get("password", "")

    if not username or not password:
        return _ok({"result": False, "msg": "Username or password incorrect"})

    player = _player_by_username(username)
    if player and player.get("password") == password:
        return _ok({"result": True, "msg": "OK"})
    else:
        return _ok({"result": False, "msg": "Username or password incorrect"})

# ENDPOINT: /player/update(PUT)
# Validate player's score and games played
@app.route(route="player/update", methods=["PUT"])
@app.function_name(name="player_update")
def player_update(req: func.HttpRequest) -> func.HttpResponse:
    body = _get_body(req)
    username = body.get("username", "")
    add_gp = int(body.get("add_to_games_played", 0))
    add_sc = int(body.get("add_to_score", 0))

    player = _player_by_username(username)
    if not player:
        return _ok({"result": False, "msg": "Player does not exist"})

    player["games_played"] = int(player.get("games_played", 0)) + add_gp
    player["total_score"] = int(player.get("total_score", 0)) + add_sc

    # Replace item requires (id, partition_key=/id)
    PLAYER_C.replace_item(item=player["id"], body=player)
    return _ok({"result": True, "msg": "OK"})

# ENDPOINT: /prompt/create(POST)
# Allow a player to create a new prompt
@app.route(route="prompt/create", methods=["POST"])
@app.function_name(name="prompt_create")
def prompt_create(req: func.HttpRequest) -> func.HttpResponse:
    body = _get_body(req)
    username = body.get("username", "")
    text = body.get("text", "")
    tags = body.get("tags", []) or []

    # Player existence
    if not _player_by_username(username):
        return _ok({"result": False, "msg": "Player does not exist"})

    # Length validation (20..120)
    if not (20 <= len(text) <= 120):
        return _ok({"result": False, "msg": "Prompt less than 20 characters or more than 120 characters"})

    # Language detection and confidence
    try:
        detected, score = _translate_detect(text)
    except Exception as e:
        logging.error(f"Translate detect error: {e}")
        # If detection fails entirely, treat as unsupported
        return _ok({"result": False, "msg": "Unsupported language"})

    if float(score) < 0.2:
        return _ok({"result": False, "msg": "Unsupported language"})

    # Build full texts array (original + translations)
    texts = _translate_to_all(text)

    # De-duplicate tags (case-insensitive set)
    dedup = []
    seen = set()
    for t in tags:
        k = t.lower()
        if k not in seen:
            dedup.append(t)
            seen.add(k)

    doc = {
        "id": str(uuid.uuid4()),
        "username": username,   
        "texts": texts,
        "tags": dedup
    }
    PROMPT_C.create_item(doc)
    return _ok({"result": True, "msg": "OK"})


# ENDPOINT: /prompt/moderate(POST)
# Approve or reject a prompt
@app.route(route="prompt/moderate", methods=["POST"])
@app.function_name(name="prompt_moderate")
def prompt_moderate(req: func.HttpRequest) -> func.HttpResponse:
    body = _get_body(req)
    ids: list[str] = body.get("prompt-ids", [])
    out: list[dict] = []

    if not ids:
        return _ok([])

    for pid in ids:
        # Find by id across partitions
        q = "SELECT * FROM c WHERE c.id = @id"
        rows = list(PROMPT_C.query_items(q, parameters=[
                    {"name": "@id", "value": pid}], enable_cross_partition_query=True))
        if not rows:
            continue
        prompt = rows[0]
        try:
            avg = _content_safety_average_english(prompt.get("texts", []))
        except Exception as e:
            logging.error(f"Content Safety error for {pid}: {e}")
            avg = 0.0
        outcome = bool(avg > 2.0)
        out.append({"prompt-id": pid, "outcome": outcome,
                   "average_severity": round(avg, 2)})

    return _ok(out)

# ENDPOINT: /prompt/delete(POST)
# Delete a prompt by ID and username
@app.route(route="prompt/delete", methods=["POST"])
@app.function_name(name="prompt_delete")
def prompt_delete(req: func.HttpRequest) -> func.HttpResponse:
    body = _get_body(req)
    player = body.get("player", "")

    q = "SELECT c.id FROM c WHERE c.username = @u"
    rows = list(PROMPT_C.query_items(q, parameters=[
                {"name": "@u", "value": player}], enable_cross_partition_query=True))

    count = 0
    for r in rows:
        try:
            PROMPT_C.delete_item(
                item=r["id"], partition_key=player)  # PK is /id
            count += 1
        except exceptions.CosmosResourceNotFoundError:
            pass

    return _ok({"result": True, "msg": f"{count} prompts deleted"})


# ENDPOINT: /utils/get(GET) input: {"players":[...], "tag_list":[...]}  -> return full prompts
# Utility to read all data of a given type (player or prompt)
@app.route(route="utils/get", methods=["GET"])
@app.function_name(name="utils_get")
def utils_get(req: func.HttpRequest) -> func.HttpResponse:
    body = _get_body(req)
    players = body.get("players", []) or []
    tag_list = body.get("tag_list", []) or []

    if not players or not tag_list:
        return _ok([])

    # Build an OR filter for tags; since tags is array, we can use ARRAY_CONTAINS in Cosmos SQL
    # We'll run per-player query (since partition key=/username).
    results = []
    tag_set = {t.lower() for t in tag_list}

    for p in players:
        # Query all prompts for player partition quickly
        itt = PROMPT_C.read_all_items(partition_key=p)
        for doc in itt:
            tags = [t.lower() for t in (doc.get("tags") or [])]
            if any(t in tag_set for t in tags):
                results.append(doc)

    return _ok(results)

# Triggered when new items are created in the 'player' container
@app.cosmos_db_trigger(
    arg_name="docs",
    connection="AzureCosmosDBConnectionString",   
    database_name="quiplash",
    container_name="player",
    lease_container_name="leases",
    create_lease_container_if_not_exists=True
)
@app.function_name(name="utils_welcome")
def utils_welcome(docs: func.DocumentList) -> None:
    """
    Fires on inserts/updates to 'player' container.
    Inserts a translated 'Welcome to COMP3207, <username>' prompt once per user.
    """
    if not docs:
        return

    for d in docs:
        try:
            payload = json.loads(d.to_json())  # convert Document -> dict
            username = payload.get("username")
            if not username:
                continue

            # idempotency: skip if welcome already exists for this user
            base_text = f"Welcome to COMP3207, {username}"
            exists = list(PROMPT_C.query_items(
                query=("""
                    SELECT TOP 1 c.id
                    FROM c
                    JOIN t IN c.texts
                    WHERE c.username = @u AND t.language = 'en' AND t.text = @txt
                """),
                parameters=[{"name": "@u", "value": username},
                            {"name": "@txt", "value": base_text}],
                enable_cross_partition_query=True
            ))
            if exists:
                continue  # already created previously

            # build full translations and insert
            texts = _translate_to_all(base_text)
            PROMPT_C.create_item({
                "id": str(uuid.uuid4()),
                "username": username,   # prompt PK is /username
                "texts": texts,
                "tags": []             
            })

            logging.info(f"utils_welcome: inserted welcome for {username}")

        except Exception as e:
            logging.error(f"utils_welcome error: {e}")

