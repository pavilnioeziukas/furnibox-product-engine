from config import load_settings
from odoo_client import OdooClient


def main():
    settings = load_settings()
    client = OdooClient(settings)
    uid = client.authenticate()

    print(f"Odoo API ryšys veikia. UID = {uid}")


if __name__ == "__main__":
    main()