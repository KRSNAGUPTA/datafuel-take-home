import requests

baseUrl = 'http://127.0.0.1:8765'

headerKey = 'X-Api-Key'
headerVal = 'dfhire-2026'

custom_headers ={
    headerKey: headerVal
}

r = requests.get(f"{baseUrl}/v1/stores", headers=custom_headers)

print(r.json())