import xmlrpc.client

URL = "https://odoo.furnibox.lt"
DB = "odoodb"
USERNAME = "e.kriukonis@gmail.com"

api_key = input("API Key: ")

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, api_key, {})

if not uid:
    print("Prisijungti nepavyko.")
    quit()

print(f"Prisijungta. UID = {uid}")

models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

products = models.execute_kw(
    DB,
    uid,
    api_key,
    "product.product",
    "search_read",
    [[]],
    {
        "fields": [
            "default_code",
            "name",
            "active"
        ],
        "limit": 10,
        "order": "default_code"
    }
)

print()

for p in products:
    print(
        p["default_code"],
        "|",
        p["name"],
        "|",
        p["active"]
    )