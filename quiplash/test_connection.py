from azure.cosmos import CosmosClient
import os

connection_string = os.environ.get("AzureCosmosDBConnectionString")
client = CosmosClient.from_connection_string(connection_string)
database = client.get_database_client("quiplash")
container = database.get_container_client("player")

print("✅ Connected to Cosmos DB successfully!")
