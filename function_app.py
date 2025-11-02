# ---------------------------------------------------------------------------------
# This Azure Function App implements the Quiplash backend. 
# It provides REST-style HTTP endpoints for:
#   - Player registration, login, and score updates
#   - Prompt creation, moderation, and deletion
#   - Utility endpoints for testing and data retrieval
# Data is stored in Azure Cosmos DB with two containers:
#   1. player (partition key: /username)
#   2. prompt (partition key: /username)
# ---------------------------------------------------------------------------------

import logging
import json
import os
import uuid
import azure.functions as func
from azure.cosmos import CosmosClient, exceptions

# ---------------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------------

# Environment variable set in Azure Portal
COSMOS_CONN_STR = os.getenv("COSMOS_CONNECTION_STRING")

# Database and container names 
DB_NAME = "quiplash"
PLAYER_CONTAINER_NAME = "player"
PROMPT_CONTAINER_NAME = "prompt"

# Create Cosmos client and container handles 
cosmos_client = CosmosClient.from_connection_string(COSMOS_CONN_STR)
database = cosmos_client.get_database_client(DB_NAME)
player_container = database.get_container_client(PLAYER_CONTAINER_NAME)
prompt_container = database.get_container_client(PROMPT_CONTAINER_NAME)

# Auth level set to ANONYMOUS so routes are public 
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ------------------------------------------------------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------------------------------------------------------

def _json_response(data: dict, status=200):
    """Return consistent JSON response."""
    return func.HttpResponse(
        json.dumps(data, default=str),
        mimetype="application/json",
        status_code=status
    )

# ------------------------------------------------------------------------------------------------------------
# ENDPOINT: /utils/welcome
# ------------------------------------------------------------------------------------------------------------
@app.function_name(name="utils_welcome")
@app.route(route="utils/welcome", methods=["GET"])
def utils_welcome(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"result": True, "msg": "Welcome to Quiplash API"})

# ------------------------------------------------------------------------------------------------------------
# ENDPOINT: /player/register
# register a new player with validation rules 
# ------------------------------------------------------------------------------------------------------------
@app.function_name(name="player_register")
@app.route(route="player/register", methods=["POST"])
def player_register(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    username = body.get("username")
    password = body.get("password")

    # Validation rules
    if not username or len(username) < 5 or len(username) > 12:
        return _json_response({"result": False,
                               "msg": "Username less than 5 characters or more than 12 characters"})
    if not password or len(password) < 8 or len(password) > 12:
        return _json_response({"result": False,
                               "msg": "Password less than 8 characters or more than 12 characters"})
    

    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    existing = list(player_container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    if existing:
        return _json_response({"result": False, "msg": "Username already exists"})
    
    player_doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "password": password,
        "games_played": 0,
        "total_score": 0
    }

    try:
        player_container.create_item(player_doc)
    except Exception as e:
        logging.error(f"Player registration failed: {e}")
        return _json_response({"result": False, "msg": "Internal error"}, 500)
    
    return _json_response({"result": True, "msg": "OK"})

#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /player/login
# Validate player credentials 
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="player_login")
@app.route(route="player/login", methods=["POST"])
def player_login(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    username = body.get("username")
    password = body.get("password")

    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value":username}]
    results = list(player_container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    if not results:
        return _json_response({"result": False, "msg": "Username not found"})
    if results[0]["password"] != password:
        return _json_response({"result": False, "msg": "Incorrect password"})
    
    return _json_response({"result": True, "msg": "OK"})


#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /player/update
# Validate player's score and games played 
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="player_update")
@app.route(route="player/update", methods=["POST"])
def player_update(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    username = body.get("username")
    score = body.get("score")

    if username is None or score is None:
        return _json_response({"result": False, "msg": "Missing fields"}, 400)
    
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    results = list(player_container.query_items(query-query, parameters=params, enable_cross_partition_query=True))

    if not results:
        return _json_response({"result": False, "msg": "Username not found"})
    
    player = results[0]
    player["games_played"] += 1
    player["total_score"] += score

    try:
        player_container.replace_item(player["id"], player)
    except Exception as e:
        logging.error(f"Player update failed: {e}")
        return _json_response({"result": False, "msg": "Internal error"}, 500)
    
    return _json_response({"result": True, "msg": "OK"})


#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /prompt/create
# Allow a player to create a new prompt
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="prompt_create")
@app.route(route="prompt/create", methods=["POST"])
def prompt_create(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    username = body.get("username")
    prompt_text = body.get("prompt_text")

    if not username or not prompt_text:
        return _json_response({"result": False, "msg": "Missing username or prompt_text"}, 400)
    
    query = "SELECT * FROM c WHERE c.username = @u"
    params = [{"name": "@u", "value": username}]
    player_exists = list(player_container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    if not player_exists:
        return _json_response({"result": False, "msg": "Username not found"})
    

    prompt_doc = {
        "id": str(uuid.uuid4()),
        "username": username,
        "prompt_text": prompt_text,
        "approved": False
    }
    
    try: 
        created = prompt_container.create_item(prompt_doc)
        return _json_response({"result": True, "msg": "OK", "prompt_id": created["id"]})
    except Exception as e:
        logging.error(f"Prompt creation failed: {e}")
        return _json_response({"result": False, "msg": "Internal error"}, 500)


#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /prompt/moderate
# Approve or reject a prompt 
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="prompt_moderate")
@app.route(route="prompt/moderate", methods=["POST"])
def prompt_moderate(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    prompt_id = body.get("prompt_id")
    username = body.get("username")
    approved = body.get("approved")

    if not prompt_id or not username or approved is None:
        return _json_response({"result": False, "msg": "Missing prompt_id, username, or approved"}, 400)
    
    try: 
        prompt_item = prompt_container.read_item(item=prompt_id, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return _json_response({"result": False, "msg": "Prompt not found"})
    
    prompt_item["approved"] = bool(approved)

    try:
        prompt_container.replace_item(prompt_item["id"], prompt_item)
    except Exception as e:
        logging.error(f"Prompt moderation failed: {e}")
        return _json_response({"result": False, "msg": "Internal error"}, 500)
    
    msg = "Prompt approved" if approved else "Prompt rejected"
    return _json_response({"result": True, "msg": msg})


#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /prompt/delete
# Delete a prompt by ID and username
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="prompt_delete")
@app.route(route="prompt/delete", methods=["POST"])
def prompt_delete(req: func.HttpRequest) -> func.HttpResponse:
    try: 
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    prompt_id = body.get("prompt_id")
    username = body.get("username")

    if not prompt_id or not username:
        return _json_response({"result": False, "msg": "Missing prompt_id or username"}, 400)
    
    try:
        prompt_container.delete_item(item=prompt_id, partition_key=username)
    except exceptions.CosmosResourceNotFoundError:
        return _json_response({"result": False, "msg": "Prompt not found"})
    except Exception as e:
        logging.error(f"Prompt delete failed: {e}")
        return _json_response({"result": True, "msg": "Deleted"})
    
    return _json_response({"result": True, "msg": "Deleted"})


#---------------------------------------------------------------------------------------------------------------------
# ENDPOINT: /utils/get
# Utility to read all data of a given type (player or prompt)
#---------------------------------------------------------------------------------------------------------------------
@app.function_name(name="utils_get")
@app.route(route="utils/get", methods=["POST"])
def utils_get(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"result": False, "msg": "Invalid JSON"}, 400)
    
    data_type = body.get("type")
    if data_type not in ["player", "prompt"]:
        return _json_response({"result": False, "msg": "Invalid type"}, 400)
    
    container = player_container if data_type == "player" else prompt_container
    try:
        items = list(container.read_all_items())
        return _json_response({"result": True, "data": items})
    except Exception as e:
        logging.error(f"Utils get failed: {e}")
        return _json_response({"result": False, "msg": "Internal error"}, 500)