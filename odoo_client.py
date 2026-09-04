import xmlrpc.client

class OdooClient:
    def __init__(self, settings):
        self.settings = settings
        self.uid = None
        self.common = xmlrpc.client.ServerProxy(
            f"{settings.url}/xmlrpc/2/common", allow_none=True
        )
        self.models = xmlrpc.client.ServerProxy(
            f"{settings.url}/xmlrpc/2/object", allow_none=True
        )

    def authenticate(self):
        uid = self.common.authenticate(
            self.settings.db,
            self.settings.login,
            self.settings.api_key,
            {},
        )
        if not uid:
            raise PermissionError("Odoo autentifikacija nepavyko.")
        self.uid = int(uid)
        return self.uid

    def search_read_all(self, model, domain, fields, order="id asc", context=None, batch_size=1000):
        if self.uid is None:
            self.authenticate()
        rows = []
        offset = 0
        while True:
            batch = self.models.execute_kw(
                self.settings.db,
                self.uid,
                self.settings.api_key,
                model,
                "search_read",
                [domain],
                {
                    "fields": fields,
                    "limit": batch_size,
                    "offset": offset,
                    "order": order,
                    "context": context or {},
                },
            )
            rows.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
        return rows

    def execute(self, model, method, args=None, kwargs=None):
        """Execute an authenticated Odoo model method.

        Mutating tools use this explicit method so every write remains visible in
        the calling use case instead of being hidden inside a generic repository.
        """
        if self.uid is None:
            self.authenticate()
        return self.models.execute_kw(
            self.settings.db,
            self.uid,
            self.settings.api_key,
            model,
            method,
            args or [],
            kwargs or {},
        )

    def ensure_external_ids(self, model, record_ids, batch_size=500):
        """Sugeneruoja trūkstamus Odoo ``__export__`` ID per standartinį eksportą.

        ``export_data`` nekeičia verslo laukų. Eksportuojant techninį ``id``
        lauką Odoo sukuria External ID tiems įrašams, kurie jo dar neturi.
        """
        if self.uid is None:
            self.authenticate()

        unique_ids = sorted({int(record_id) for record_id in record_ids})
        exported = 0
        for offset in range(0, len(unique_ids), batch_size):
            batch = unique_ids[offset:offset + batch_size]
            self.models.execute_kw(
                self.settings.db,
                self.uid,
                self.settings.api_key,
                model,
                "export_data",
                [batch, ["id"]],
                {"context": {"import_compat": True}},
            )
            exported += len(batch)
        return exported

    def products(self):
        return self.search_read_all(
            "product.product",
            [],
            [
                "id", "default_code", "name", "active",
                "product_tmpl_id", "categ_id", "uom_id",
                "type", "standard_price", "currency_id", "write_date",
            ],
            context={"active_test": False},
        )

    def products_by_ids(self, product_ids):
        """Grąžina kainų eksportui reikalingus produktų laukus."""
        unique_ids = sorted({int(product_id) for product_id in product_ids})
        if not unique_ids:
            return []
        return self.search_read_all(
            "product.product",
            [["id", "in", unique_ids]],
            ["id", "default_code", "name"],
            context={"active_test": False},
        )

    def boms(self):
        return self.search_read_all(
            "mrp.bom",
            [],
            [
                "id", "code", "active", "product_tmpl_id", "product_id",
                "product_qty", "product_uom_id", "type",
                "company_id", "write_date",
            ],
            context={"active_test": False},
        )

    def bom_lines(self):
        return self.search_read_all(
            "mrp.bom.line",
            [],
            [
                "id", "bom_id", "product_id", "product_qty",
                "product_uom_id", "sequence", "company_id", "write_date",
            ],
        )

    def purchase_order_lines(self):
        return self.search_read_all(
            "purchase.order.line",
            [["order_id.state", "in", ["purchase", "done"]]],
            [
                "id", "order_id", "partner_id", "product_id",
                "product_qty", "price_unit", "currency_id",
                "date_order", "company_id", "write_date",
            ],
            order="product_id asc, date_order desc, id desc",
        )
