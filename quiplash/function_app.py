import azure.functions as func
import json
import logging
import os
import uuid
from azure.cosmos import CosmosClient, exceptions

# Initialize app
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Read Cosmos DB connection from environment variables
COSMOS_CONN_STR = os.getenv("COSMOS_CONNECTION_STRING")
DATABASE_NAME = "quiplash"
CONTAINER_NAME = "player"

client = CosmosClient.from_connection_string(COSMOS_CONN_STR)
database = client.get_database_client(DATABASE_NAME)
container = database.get_container_client(CONTAINER_NAME)

@app.function_name(name="player_register")
@app.route(route="player/register", methods=["POST"])
def player_register(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        username = data.get("username")
        email = data.get("email")
        password = data.get("password")

        if not username or not email or not password:
            return func.HttpResponse(
                json.dumps({"result": False, "msg": "Missing fields"}),
                status_code=400,
                mimetype="application/json"
            )

        # Check if user already exists
        query = f"SELECT * FROM c WHERE c.email = '{email}'"
        existing_users = list(container.query_items(query=query, enable_cross_partition_query=True))
        if existing_users:
            return func.HttpResponse(
                json.dumps({"result": False, "msg": "User already exists"}),
                status_code=409,
                mimetype="application/json"
            )

        # Insert new player
        new_user = {
            "id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "password": password,
            "games_played": 0,
            "total_score": 0
        }
        container.create_item(new_user)

        return func.HttpResponse(
            json.dumps({"result": True, "msg": "User registered successfully"}),
            status_code=201,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(str(e))
        return func.HttpResponse(
            json.dumps({"result": False, "msg": "Internal server error"}),
            status_code=500,
            mimetype="application/json"
        )
