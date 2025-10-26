import logging
import json
import os
import uuid
import azure.functions as func
from azure.cosmos import CosmosClient, exceptions

# ---------------------------------------------------------------------------------
# CONFIG / SETUP
# ---------------------------------------------------------------------------------

# This MUST match the key you put in local.settings.json
COSMOS_CONN_STR = os.getenv("COSMOS_CONNECTION_STRING")

DB_NAME = "quiplash"
PLAYER_CONTAINER_NAME = "player"

# Create Cosmos clients once (good practice for Functions)
cosmos_client = CosmosClient.from_connection_string(COSMOS_CONN_STR)
database = cosmos_client.get_database_client(DB_NAME)
player_container = database.get_container_client(PLAYER_CONTAINER_NAME)
prompt_container = database.get_container_client("prompt")


# Create Azure FunctionApp with FUNCTION-level auth (as required in spec)
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ---------------------------------------------------------------------------------
# /player/register
# Spec:
#   POST body:
#     {"username": "string", "password": "string"}
#
#   Success:
#     {"result": true, "msg": "OK"}
#
#   Failures (exact wording required):
#     {"result": false, "msg": "Username less than 5 characters or more than 12 characters"}
#     {"result": false, "msg": "Password less than 8 characters or more than 12 characters"}
#     {"result": false, "msg": "Username already exists"}
#
#   Also:
#     - games_played: 0
#     - total_score: 0
#     - username must be unique
#     - username len 5..12
#     - password len 8..12
# ---------------------------------------------------------------------------------

# ---------------------------------------------------------------------------------
# /player/login
# Spec:
#   POST body: {"username": "string", "password": "string"}
#
#   Success:
#     {"result": true, "msg": "OK"}
#
#   Failures:
#     {"result": false, "msg": "Username not found"}
#     {"result": false, "msg": "Incorrect password"}
# ---------------------------------------------------------------------------------

@app.function_name(name="player_login")
@app.route(route="player/login", methods=["POST"])
def player_login(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("player/login called")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    username = body.get("username")
    password = body.get("password")

    # 1. Check if user exists
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    results = list(player_container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True
    ))

    if not results:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Username not found"}),
            mimetype="application/json"
        )

    # 2. Verify password
    player = results[0]
    if player["password"] != password:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Incorrect password"}),
            mimetype="application/json"
        )

    # 3. Success
    return func.HttpResponse(
        json.dumps({"result": True, "msg": "OK"}),
        mimetype="application/json"
    )


# ---------------------------------------------------------------------------------
# /player/update
# Spec:
#   POST body: {"username": "string", "score": number}
#
#   Success:
#     {"result": true, "msg": "OK"}
#
#   Failure:
#     {"result": false, "msg": "Username not found"}
# ---------------------------------------------------------------------------------

@app.function_name(name="player_update")
@app.route(route="player/update", methods=["POST"])
def player_update(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("player/update called")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    username = body.get("username")
    score = body.get("score")

    if username is None or score is None:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Missing fields"}),
            mimetype="application/json",
            status_code=400
        )

    # 1. Check if player exists
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    results = list(player_container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True
    ))

    if not results:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Username not found"}),
            mimetype="application/json"
        )

    player = results[0]
    player["games_played"] += 1
    player["total_score"] += score

    try:
        player_container.replace_item(player["id"], player)
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"Update failed: {e}")
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Internal error"}),
            mimetype="application/json",
            status_code=500
        )

    return func.HttpResponse(
        json.dumps({"result": True, "msg": "OK"}),
        mimetype="application/json"
    )


# ---------------------------------------------------------------------------------
# /prompt/add
# Spec:
#   POST body: {"username": "string", "prompt_text": "string"}
#
#   Success:
#     {"result": true, "msg": "OK"}
#
#   Failure:
#     {"result": false, "msg": "Username not found"}
# ---------------------------------------------------------------------------------

@app.function_name(name="prompt_add")
@app.route(route="prompt/add", methods=["POST"])
def prompt_add(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("prompt/add called")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    username = body.get("username")
    prompt_text = body.get("prompt_text")

    if not username or not prompt_text:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Missing fields"}),
            mimetype="application/json",
            status_code=400
        )

    # Check if player exists before adding a prompt
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    results = list(player_container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True
    ))

    if not results:
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Username not found"}),
            mimetype="application/json"
        )

    prompt_doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "prompt_text": prompt_text
    }

    try:
        prompt_container.create_item(prompt_doc)
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"Prompt insert failed: {e}")
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Internal error"}),
            mimetype="application/json",
            status_code=500
        )

    return func.HttpResponse(
        json.dumps({"result": True, "msg": "OK"}),
        mimetype="application/json"
    )

# ---------------------------------------------------------------------------------
# /prompt/get
# Spec:
#   GET or POST: optional {"username": "string"}
#   If username provided → return only their prompts
#   Else → return all prompts
#
#   Success:
#     {"result": true, "prompts": [list of prompt_texts]}
# ---------------------------------------------------------------------------------

@app.function_name(name="prompt_get")
@app.route(route="prompt/get", methods=["GET", "POST"])
def prompt_get(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("prompt/get called")

    try:
        body = req.get_json()
        username = body.get("username") if body else None
    except ValueError:
        username = None

    try:
        if username:
            query = "SELECT c.prompt_text FROM c WHERE c.username = @u"
            params = [{"name": "@u", "value": username}]
            items = list(prompt_container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True
            ))
        else:
            query = "SELECT c.prompt_text FROM c"
            items = list(prompt_container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))

        prompts = [item["prompt_text"] for item in items]

        return func.HttpResponse(
            json.dumps({"result": True, "prompts": prompts}),
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Prompt query failed: {e}")
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Internal error"}),
            mimetype="application/json",
            status_code=500
        )


@app.function_name(name="player_register")
@app.route(route="player/register", methods=["POST"])
def player_register(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("player/register called")

    # Parse request body
    try:
        body = req.get_json()
    except ValueError:
        # Spec says: assume well-formed JSON, so this shouldn't be tested,
        # but let's be defensive.
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Invalid JSON"}),
            mimetype="application/json",
            status_code=400
        )

    username = body.get("username")
    password = body.get("password")

    # 1. Validate username length (5..12)
    if (username is None) or (len(username) < 5 or len(username) > 12):
        return func.HttpResponse(
            json.dumps({
                "result": False,
                "msg": "Username less than 5 characters or more than 12 characters"
            }),
            mimetype="application/json"
        )

    # 2. Validate password length (8..12)
    if (password is None) or (len(password) < 8 or len(password) > 12):
        return func.HttpResponse(
            json.dumps({
                "result": False,
                "msg": "Password less than 8 characters or more than 12 characters"
            }),
            mimetype="application/json"
        )

    # 3. Check if username already exists
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    existing = list(player_container.query_items(
        query=query,
        parameters=params,
        enable_cross_partition_query=True
    ))

    if len(existing) > 0:
        return func.HttpResponse(
            json.dumps({
                "result": False,
                "msg": "Username already exists"
            }),
            mimetype="application/json"
        )

    # 4. Insert new player document
    new_player = {
        "id": str(uuid.uuid4()),      # partition key is /id
        "username": username,
        "password": password,
        "games_played": 0,
        "total_score": 0
    }

    try:
        player_container.create_item(new_player)
    except exceptions.CosmosHttpResponseError as e:
        logging.error(f"Cosmos DB insert failed: {e}")
        # The spec doesn't define an error message here, but let's return something
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Internal error"}),
            mimetype="application/json",
            status_code=500
        )

    # 5. Success response (must match spec exactly)
    return func.HttpResponse(
        json.dumps({
            "result": True,
            "msg": "OK"
        }),
        mimetype="application/json"
    )

