"""Furnibox Product Engine GUI v12 su pasikeitusių BOM versijų generatoriumi."""

from tkinter import ttk

from app_v11 import FurniboxAppV11, first_existing


class FurniboxAppV12(FurniboxAppV11):
    def _build_ui(self):
        super()._build_ui()
        actions = self.bom_button.master
        separator = next(child for child in actions.winfo_children() if isinstance(child, ttk.Separator))
        self.version_button = ttk.Button(
            actions,
            text="13. Paruošti esamų BOM naujas versijas",
            command=lambda: self.run_script(first_existing("bom_version_import_v1.py")),
            style="Action.TButton",
        )
        self.version_button.pack(fill="x", pady=3, before=separator)

    def _set_buttons_state(self, state: str):
        super()._set_buttons_state(state)
        if hasattr(self, "version_button"):
            self.version_button.configure(state=state)


if __name__ == "__main__":
    app = FurniboxAppV12()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
