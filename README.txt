COMP3207 Coursework 1 - Part 1
Name: Yasaswini Kalavakuri (yk3g23)

Cosmos DB Configuration:
-------------------------
Database Name: quiplash
Containers:
  - player   (partition key: /id)
  - prompt   (partition key: /username)
Region: France Central

Functions Implemented:
-----------------------
Player Functions:
  - POST /player/register     : Register a new player
  - GET  /player/login        : Login and retrieve player details
  - PUT  /player/update       : Update player score

Prompt Functions:
  - POST /prompt/create       : Create a new prompt
  - POST /prompt/delete       : Delete an existing prompt
  - POST /prompt/moderate     : Moderate prompt content

Utility Functions:
  - GET /utils/get            : Utility endpoint used for testing

Deployment Status:
------------------
✅ All endpoints tested locally
✅ Successfully deployed to Azure
✅ Endpoints returning expected outputs
COMP3207 Coursework 1 - Part 1
Name: Yasaswini Kalavakuri (yk3g23)

Cosmos DB:
Database: quiplash
Containers: player, prompt
Region: France Central
Partition Keys: player (/id), prompt (/username)

Functions Implemented:
- POST /player/register
- GET  /player/login
- PUT  /player/update
- POST /prompt/create
- POST /prompt/delete
- POST /prompt/moderate
- GET  /utils/get

All endpoints tested locally and deployed successfully.
