# Quiplash Cloud Function App (COMP3207 Coursework)

This Azure Function App implements the backend for a Quiplash-style game.
It includes endpoints for player registration, login, score updates, and prompt management.

## Endpoints

| Route | Method | Description |
|--------|--------|-------------|
| /utils/welcome | GET | Health check |
| /player/register | POST | Register new player |
| /player/login | POST | Login existing player |
| /player/update | POST | Update score and games played |
| /prompt/create | POST | Add a new prompt |
| /prompt/moderate | POST | Approve or reject a prompt |
| /prompt/delete | POST | Delete a prompt |
| /utils/get | POST | Retrieve all players or prompts |

Database: Azure Cosmos DB (`player` and `prompt` containers, partition key `/username`)

Author: Yasaswini Kalavakuri
