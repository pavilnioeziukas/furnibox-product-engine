# Furnibox Product Engine web pilotas

Web pilotas paleidžia esamus Python scenarijus serveryje. Naudotojui reikia tik naršyklės.

## Saugumo ribos

- Production naudojama tik nuskaitymui.
- Web sąsajoje nėra Odoo importo, `create`, `write`, `unlink` ar patvirtinimo veiksmų.
- Sugeneruoti Excel ir JSON failai tik atsisiunčiami.
- Prieigą saugo bendras piloto slaptažodis.

## Paleidimas lokaliai su Docker

1. Pagal `.env.web.example` sukurti `.env.web` ir užpildyti Odoo bei web slaptažodžius.
2. Paleisti:

```powershell
docker build -t furnibox-product-engine .
docker run --rm -p 8080:8080 --env-file .env.web -v furnibox-web-state:/app/web_state furnibox-product-engine
```

3. Atidaryti `http://localhost:8080`.

## Cloud reikalavimai

- vienas konteinerio egzempliorius (`workers=1`);
- nuolatinis diskas prijungtas prie `/app/web_state`;
- abu bendrų duomenų kintamieji (`FURNIBOX_SHARED_DATA` ir `FURNIBOX_SHARED_DATA_DIR`) rodo į `/app/web_state/shared_data`;
- Odoo ir web paslaptys pateikiamos tik per aplinkos kintamuosius;
- HTTPS;
- prieiga prie `https://odoo.furnibox.lt`;
- ilgiausias užklausos / darbo laikas bent 30 min.

`/health` grąžina diegimo būsenos patikrą.

## Railway diegimas

1. Railway sukurti projektą iš šio GitHub repo ir pasirinkti Dockerfile diegimą.
2. Prijungti volume prie `/app/web_state`.
3. Sukurti kintamuosius pagal `.env.web.example` (slaptažodžių į Git nekelti).
4. Sugeneruoti viešą HTTPS domeną ir patikrinti `/health`.

`railway.json` jau aprašo Docker build, sveikatos patikrą ir proceso perkrovimo taisyklę.
