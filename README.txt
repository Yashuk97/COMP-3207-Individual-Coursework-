COMP3207 Coursework 1 - Part 1
Name: Yasaswini Kalavakuri (yk3g23)

Deployment URL:
https://quiplash-func-yasaswini.azurewebsites.net

Function App Key:
lQmklH_K2rnD3e4YdonwH0j6bm1M6ZKgMg8cUo7l0CDrAzFuujcDmw==

Cosmos DB:
Database: quiplash
Containers: player, prompt
Region: France Central
Partition Keys: player (/id), prompt (/username)

Translation:
Endpoint: https://api.cognitive.microsofttranslator.com/
Region: francecentral

Content Safety:
Endpoint: https://quiplash-contentsafety-yasaswini.cognitiveservices.azure.com/

Functions Implemented:
- POST /player/register
- GET  /player/login
- PUT  /player/update
- POST /prompt/create
- POST /prompt/delete
- POST /prompt/moderate
- GET  /utils/get

All endpoints tested locally and deployed successfully.
