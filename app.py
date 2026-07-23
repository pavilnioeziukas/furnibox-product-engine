"""Canonical Furnibox Product Engine launcher.

Paleiskite tik šį failą. Dabartinė pilna GUI versija yra realizuota
``app_v12.py`` ir paveldi bazinius 1–8 veiksmus iš ``app_v7.py``.
"""

from app_v12 import FurniboxAppV12


def main() -> None:
    app = FurniboxAppV12()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()


if __name__ == "__main__":
    main()
