"""Furnibox Product Engine desktop interface v5.\n\nGUI paleidžia naujausias patikrintas proceso scenarijų versijas.\n"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

from dotenv import dotenv_values


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

ENVIRONMENTS = {
    "Stage": {
        "file": BASE_DIR / ".env.stage",
        "color": "#16803a",
        "description": "Testinė aplinka – leidžiama ruošti ir testuoti importus",
    },
    "Production": {
        "file": BASE_DIR / ".env",
        "color": "#b42318",
        "description": "Produkcinė aplinka – tik duomenų nuskaitymui",
    },
}


def first_existing(*names: str) -> str:
    for name in names:
        if (BASE_DIR / name).exists():
            return name
    return names[0]


class FurniboxApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Furnibox Product Engine")
        self.geometry("1040x720")
        self.minsize(900, 620)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.process: subprocess.Popen | None = None
        self.action_buttons: list[ttk.Button] = []

        self.environment = tk.StringVar(value="Stage")
        self.status = tk.StringVar(value="Pasiruošę")
        self.environment_info = tk.StringVar()

        self._configure_style()
        self._build_ui()
        self._environment_changed()
        self.after(100, self._poll_events)

    def _configure_style(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Action.TButton", padding=(12, 10), anchor="w")
        style.configure("Status.TLabel", padding=(8, 5))

    def _build_ui(self):
        outer = ttk.Frame(self, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Furnibox Product Engine", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Odoo duomenų nuskaitymas, MAP generavimas ir importo failų paruošimas",
        ).pack(anchor="w", pady=(2, 16))

        env_frame = ttk.LabelFrame(outer, text="1. Pasirinkite aplinką", padding=12)
        env_frame.pack(fill="x")
        for name in ENVIRONMENTS:
            ttk.Radiobutton(
                env_frame,
                text=name,
                value=name,
                variable=self.environment,
                command=self._environment_changed,
            ).pack(side="left", padx=(0, 18))
        self.env_badge = tk.Label(
            env_frame,
            textvariable=self.environment_info,
            fg="white",
            padx=10,
            pady=5,
            font=("Segoe UI", 9, "bold"),
        )
        self.env_badge.pack(side="left", fill="x", expand=True)

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(14, 0))
        body.columnconfigure(0, weight=0, minsize=330)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        actions = ttk.LabelFrame(body, text="2. Pasirinkite veiksmą", padding=12)
        actions.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        action_specs = [
            ("1. Patikrinti Odoo prisijungimą", lambda: self.run_script("test_odoo.py")),
            ("2. Nuskaityti Odoo duomenis", lambda: self.run_script("main.py")),
            ("3. Palyginti visus produktus", lambda: self.run_script(first_existing("product_detection_v2.py", "product_detection.py"))),
            ("4. Generuoti Reform MAP", lambda: self.run_script("reform_map.py")),
            ("5. Generuoti Odoo MAP", lambda: self.run_script("odoo_map.py")),
            # 6 žingsnis naudoja pataisytą palyginimą: galutinį Product Detection
            # failą ir skaitinių SKU pradinių nulių normalizavimą.
            ("6. Palyginti MAP", lambda: self.run_script(first_existing(
                "map_comparison_v4_commented.py",
                "map_comparison_v2.py",
                "map_comparison.py",
            ))),
            # 7 žingsnis pirmiausia renkasi naujausią patikrintą produktų
            # importo generatorių, o senesnes versijas palieka tik atsargai.
            ("7. Paruošti visų produktų importą", lambda: self.run_script(first_existing(
                "product_import_v6.py",
                "product_import_v5.py",
                "product_import_v4.py",
                "product_import.py",
            ))),
        ]
        for text, command in action_specs:
            button = ttk.Button(actions, text=text, command=command, style="Action.TButton")
            button.pack(fill="x", pady=3)
            self.action_buttons.append(button)

        # 8 žingsnis dar neimportuoja BOM į Odoo. Jis tik sukuria saugią
        # BOM tipų peržiūros ataskaitą, kurią patikriname prieš importą.
        self.bom_button = ttk.Button(
            actions,
            text="8. Paruošti BOM tipų peržiūrą",
            command=lambda: self.run_script("bom_type_inference_v1.py"),
            style="Action.TButton",
        )
        self.bom_button.pack(fill="x", pady=3)

        ttk.Separator(actions).pack(fill="x", pady=12)
        ttk.Button(actions, text="Atidaryti rezultatų aplanką", command=self.open_output).pack(fill="x", pady=3)
        ttk.Button(actions, text="Išvalyti žurnalą", command=self.clear_log).pack(fill="x", pady=3)
        self.stop_button = ttk.Button(actions, text="Sustabdyti", command=self.stop_process, state="disabled")
        self.stop_button.pack(fill="x", pady=(16, 3))

        log_frame = ttk.LabelFrame(body, text="3. Vykdymo eiga", padding=8)
        log_frame.grid(row=0, column=1, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(
            log_frame,
            wrap="word",
            font=("Cascadia Mono", 10),
            background="#101828",
            foreground="#f2f4f7",
            insertbackground="white",
            padx=10,
            pady=10,
            state="disabled",
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Label(footer, text="Būsena:", style="Section.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.status, style="Status.TLabel").pack(side="left")

    def _environment_changed(self):
        name = self.environment.get()
        config = ENVIRONMENTS[name]
        env_file = config["file"]
        exists = "rastas" if env_file.exists() else "NERASTAS"
        self.environment_info.set(f"{config['description']} | {env_file.name}: {exists}")
        self.env_badge.configure(background=config["color"])
        self._write_log(f"Pasirinkta aplinka: {name} ({env_file.name})\n")

    def _selected_environment(self) -> dict[str, str] | None:
        name = self.environment.get()
        env_file: Path = ENVIRONMENTS[name]["file"]
        if not env_file.exists():
            messagebox.showerror(
                "Trūksta konfigūracijos",
                f"Nerastas {env_file.name}.\n\nSukurkite failą projekto aplanke ir įrašykite Odoo prisijungimo duomenis.",
            )
            return None
        values = {key: str(value) for key, value in dotenv_values(env_file).items() if value is not None}
        required = ["ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_API_KEY"]
        missing = [key for key in required if not values.get(key, "").strip()]
        if missing:
            messagebox.showerror(
                "Nepilna konfigūracija",
                f"Faile {env_file.name} neužpildyti laukai:\n" + "\n".join(missing),
            )
            return None
        return values

    def run_script(self, script_name: str):
        if self.running:
            messagebox.showwarning("Procesas vykdomas", "Palaukite, kol baigsis dabartinis veiksmas.")
            return
        script = BASE_DIR / script_name
        if not script.exists():
            messagebox.showerror("Failas nerastas", f"Nerastas scenarijus:\n{script}")
            return
        selected_env = self._selected_environment()
        if selected_env is None:
            return

        environment_name = self.environment.get()
        self.running = True
        self._set_buttons_state("disabled")
        self.stop_button.configure(state="normal")
        self.status.set(f"Vykdoma: {script.name} [{environment_name}]")
        self._write_log("\n" + "=" * 72 + "\n")
        self._write_log(f"Paleidžiama: {script.name}\nAplinka: {environment_name}\n")
        self._write_log(f"Odoo URL: {selected_env['ODOO_URL']}\n" + "-" * 72 + "\n")

        thread = threading.Thread(
            target=self._worker,
            args=(script, selected_env, environment_name),
            daemon=True,
        )
        thread.start()

    def _worker(self, script: Path, selected_env: dict[str, str], environment_name: str):
        process_env = os.environ.copy()
        process_env.update(selected_env)
        process_env["FURNIBOX_ENVIRONMENT"] = environment_name.upper()
        process_env["PYTHONUTF8"] = "1"
        try:
            self.process = subprocess.Popen(
                [sys.executable, "-u", str(script)],
                cwd=BASE_DIR,
                env=process_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.events.put(("log", line))
            return_code = self.process.wait()
            self.events.put(("done", (return_code, script.name)))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.process = None

    def _poll_events(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "log":
                    self._write_log(str(payload))
                elif event == "done":
                    return_code, script_name = payload
                    self.running = False
                    self._set_buttons_state("normal")
                    self.stop_button.configure(state="disabled")
                    if return_code == 0:
                        self.status.set(f"Baigta: {script_name}")
                        self._write_log("-" * 72 + "\nVEIKSMAS BAIGTAS SĖKMINGAI\n")
                    else:
                        self.status.set(f"Klaida: {script_name} (kodas {return_code})")
                        self._write_log(f"-" * 72 + f"\nVEIKSMAS BAIGTAS SU KLAIDA: {return_code}\n")
                elif event == "error":
                    self.running = False
                    self._set_buttons_state("normal")
                    self.stop_button.configure(state="disabled")
                    self.status.set("Proceso paleidimo klaida")
                    self._write_log(f"\nKLAIDA: {payload}\n")
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _set_buttons_state(self, state: str):
        for button in self.action_buttons:
            button.configure(state=state)
        self.bom_button.configure(state=state)

    def stop_process(self):
        if self.process and self.process.poll() is None:
            if messagebox.askyesno("Sustabdyti", "Ar tikrai norite sustabdyti vykdomą procesą?"):
                self.process.terminate()
                self._write_log("\nPaprašyta sustabdyti procesą...\n")

    def open_output(self):
        OUTPUT_DIR.mkdir(exist_ok=True)
        try:
            os.startfile(OUTPUT_DIR)  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["xdg-open", str(OUTPUT_DIR)])
        except OSError as exc:
            messagebox.showerror("Nepavyko atidaryti", str(exc))

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _write_log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _bom_not_ready(self):
        messagebox.showinfo(
            "BOM importas",
            "BOM importo generatorių planuojama parengti kitame etape.",
        )

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("Uždaryti", "Procesas vis dar vykdomas. Ar tikrai uždaryti programą?"):
                return
            if self.process and self.process.poll() is None:
                self.process.terminate()
        self.destroy()


if __name__ == "__main__":
    app = FurniboxApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()

