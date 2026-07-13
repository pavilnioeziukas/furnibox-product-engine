import getpass
import xmlrpc.client

URL = "https://odoo.furnibox.lt"
DB = "odoodb"
USERNAME = "e.kriukonis@gmail.com"

api_key = getpass.getpass("API Key: ")

common = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common")
uid = common.authenticate(DB, USERNAME, api_key, {})

if not uid:
    print("Prisijungti nepavyko.")
    raise SystemExit(1)

print(f"Prisijungta prie Odoo. UID = {uid}")

models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object")

products = models.execute_kw(
    DB,
    uid,
    api_key,
    "product.product",
    "search_read",
    [[]],
    {
        "fields": ["id", "default_code", "name", "active"],
        "limit": 1000,
        "order": "id asc",
        "context": {"active_test": False},
    },
)

print(f"\nNuskaityta produktų: {len(products)}\n")

for product in products:
    print(
        product["id"],
        "|",
        product.get("default_code") or "",
        "|",
        product.get("name") or "",
        "|",
        product.get("active"),
    )