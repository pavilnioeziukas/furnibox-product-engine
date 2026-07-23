"""Furnibox Product Engine GUI v12 su visu BOM paruošimo procesu.

Ši versija remiasi stabilia ``app_v7`` GUI baze ir pati prideda visus
BOM proceso veiksmus (9–14). Todėl jai nereikia tarpinių ``app_v8–v11``
failų.
"""

from tkinter import ttk

from app_v7 import FurniboxApp, first_existing


class FurniboxAppV12(FurniboxApp):
    def _build_ui(self):
        super()._build_ui()
        actions = self.bom_button.master
        separator = next(
            child for child in actions.winfo_children()
            if isinstance(child, ttk.Separator)
        )

        # 9–14 žingsniai sudėti čia viena aiškia seka. Visi generatoriai tik
        # paruošia Excel failus ir patys Odoo duomenų nekeičia.
        extra_actions = [
            ("9. Paruošti vieno BOM Stage pilotą", "bom_import_pilot_v1.py"),
            (
                "10. Nuskaityti Production BOM operacijų etalonus",
                "bom_operations_reference_v1.py",
            ),
            (
                "11. Paruošti Manufacture BOM Stage pilotą",
                "bom_import_pilot_v2.py",
            ),
            (
                "11A. Paruošti produktų External ID (tik Stage)",
                "external_id_prepare_v1.py",
            ),
            (
                "12. Paruošti visų Manufacture BOM importą",
                "bom_import_manufacture_v1.py",
            ),
            (
                "13. Paruošti visų KIT ir Manufacture BOM importą",
                "bom_import_v1.py",
            ),
            (
                "14. Paruošti esamų BOM naujas versijas",
                "bom_version_import_v1.py",
            ),
        ]
        self.extra_bom_buttons = []
        for text, script_name in extra_actions:
            button = ttk.Button(
                actions,
                text=text,
                command=lambda name=script_name: self.run_script(first_existing(name)),
                style="Action.TButton",
            )
            button.pack(fill="x", pady=3, before=separator)
            self.extra_bom_buttons.append(button)

    def _set_buttons_state(self, state: str):
        super()._set_buttons_state(state)
        for button in getattr(self, "extra_bom_buttons", []):
            button.configure(state=state)


if __name__ == "__main__":
    app = FurniboxAppV12()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()