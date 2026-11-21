# Benchmark warstwy danych

Pomiar: 2026-11-21T14:42:17, Linux x86_64, Python 3.14.6, 10 działek, budżet 25 s na działkę.
Zimny = pusty cache, wszystkie źródła z sieci. Ciepły = drugie wywołanie tej samej działki i daty.
Czasy źródeł biegną równolegle, więc suma kolumn nie równa się czasowi całkowitemu.

### Zimny cache

| source | p50 ms | p95 ms | max ms | statuses |
|---|---:|---:|---:|---|
| parcel | 364 | 3518 | 3518 | ok: 10 |
| weather | 2202 | 3479 | 3479 | fallback: 1, ok: 9 |
| ortho | 1507 | 6089 | 6089 | ok: 10 |
| soil | 2243 | 5446 | 5446 | ok: 10 |
| satellite | 3879 | 6598 | 6598 | ok: 10 |
| terrain | 2560 | 5170 | 5170 | ok: 10 |
| water | 1398 | 3253 | 3253 | ok: 10 |
| forecast | 106 | 1225 | 1225 | ok: 10 |
| seasonal | 285 | 633 | 633 | ok: 10 |
| crop_hint | 620 | 821 | 821 | ok: 10 |
| **total** | 6052 | 8697 | 8697 | core ok: 10/10 |

### Ciepły cache

| source | p50 ms | p95 ms | max ms | statuses |
|---|---:|---:|---:|---|
| parcel | 0 | 0 | 0 | ok: 10 |
| weather | 4 | 5 | 5 | fallback: 1, ok: 9 |
| ortho | 6 | 9 | 9 | ok: 10 |
| soil | 4 | 6 | 6 | ok: 10 |
| satellite | 4 | 8 | 8 | ok: 10 |
| terrain | 4 | 7 | 7 | ok: 10 |
| water | 2 | 4 | 4 | ok: 10 |
| forecast | 2 | 5 | 5 | ok: 10 |
| seasonal | 1 | 3 | 3 | ok: 10 |
| crop_hint | 0 | 2 | 2 | ok: 10 |
| **total** | 10 | 11 | 11 | core ok: 10/10 |

### Działki

| działka | data | zimny ms | ciepły ms | uwagi (zimny) |
|---|---|---:|---:|---|
| 040303_2.0002.189/13 | 2026-11-21 | 7290 | 10 | - |
| 302504_5.0028.14/4 | 2025-07-15 | 6986 | 11 | - |
| 062006_2.0005.74 | 2018-08-10 | 5765 | 8 | - |
| 161002_5.0021.AR_7.337/39 | 2024-06-20 | 3206 | 10 | - |
| 021701_2.0021.254/363 | 2022-05-30 | 8697 | 9 | - |
| 142003_2.0033.37/2 | 2026-08-01 | 4183 | 10 | - |
| 200208_2.0003.2/4 | 2019-07-01 | 6339 | 9 | - |
| 280103_2.0059.352 | 2023-09-10 | 4091 | 8 | - |
| 121406_2.0015.127 | 2021-06-15 | 8146 | 7 | weather=fallback |
| 220903_2.0005.125/5 | 2017-07-20 | 3332 | 10 | - |

### Dostawcy danych w przebiegu zimnym

| source | dostawca: liczba działek |
|---|---|
| parcel | uldk.gugik.gov.pl: 10 |
| weather | opad imgw, ET0 imgw: 8; opad imgw, ET0 nasa-power: 1; opad nasa-power, ET0 imgw: 1 |
| ortho | mapy.geoportal.gov.pl: 10 |
| soil | rest.isric.org: 10 |
| satellite | planetarycomputer.microsoft.com: 10 |
| terrain | gugik-nmt-points: 10 |
| water | gugik-bdot10k-wms: 10 |
| forecast | api.open-meteo.com: 10 |
| seasonal | seasonal-api.open-meteo.com: 10 |
| crop_hint | jeodpp.jrc.ec.europa.eu: 10 |

Pogoda w poszczególnych działkach (udział dni w zwróconym zakresie):

- 040303_2.0002.189/13 (2026-11-21): opad: imgw 99%, nasa-power 1%, open-meteo-forecast 0%; ET0: imgw 78%, nasa-power 22%, open-meteo-forecast 0%
- 302504_5.0028.14/4 (2025-07-15): opad: imgw 100%; ET0: imgw 90%, nasa-power 10%
- 062006_2.0005.74 (2018-08-10): opad: imgw 98%, nasa-power 2%; ET0: nasa-power 100%
- 161002_5.0021.AR_7.337/39 (2024-06-20): opad: imgw 100%; ET0: imgw 100%
- 021701_2.0021.254/363 (2022-05-30): opad: imgw 100%; ET0: imgw 100%
- 142003_2.0033.37/2 (2026-08-01): opad: imgw 76%, nasa-power 24%; ET0: imgw 80%, nasa-power 20%
- 200208_2.0003.2/4 (2019-07-01): opad: imgw 100%; ET0: imgw 100%, nasa-power 0%
- 280103_2.0059.352 (2023-09-10): opad: imgw 90%, nasa-power 10%; ET0: imgw 100%, nasa-power 0%
- 121406_2.0015.127 (2021-06-15): opad: nasa-power 62%, imgw 38%; ET0: imgw 95%, nasa-power 5%
- 220903_2.0005.125/5 (2017-07-20): opad: imgw 100%; ET0: imgw 100%

### Wysokości terenu: czas zimny według wielkości działki

Usługa wysokości GUGiK, siatka 10 m z marginesem 50 m, najwyżej 4000 punktów.

| działka | ha | czas s | punkty | oczko m | deniwelacja m | średni spadek % |
|---|---:|---:|---:|---:|---:|---:|
| 142003_2.0033.37/2 | 1.0 | 1.47 | 924 | 10.0 | 2.1 | 1.45 |
| 200208_2.0003.2/4 | 7.2 | 5.09 | 3186 | 10.0 | 7.2 | 2.32 |
| 161002_5.0021.AR_7.337/39 | 38.8 | 3.25 | 3990 | 13.5 | 5.2 | 0.94 |
| 302504_5.0028.14/4 | 76.7 | 2.38 | 3969 | 20.5 | 6.4 | 1.0 |
| 321404_2.0022.53 | 138.3 | 2.67 | 4032 | 29.7 | 10.4 | 1.37 |

### Opad i ET0: stacje IMGW a siatka NASA POWER, okna 60 dni

Suma w oknie 60 dni dla centroidu działki. Różnica = IMGW minus NASA POWER.

| działka | okno | opad IMGW mm | opad POWER mm | różnica mm | posterunek (km) | ET0 IMGW mm | ET0 POWER mm | stacja synoptyczna (km) |
|---|---|---:|---:|---:|---|---:|---:|---|
| 040303_2.0002.189/13 | 2018-05-01..2018-06-29 | 73.5 | 87.9 | -14.4 | NOWY JASINIEC (10.8) | 257.3 | 232.4 | TORUŃ (39.8) |
| 040303_2.0002.189/13 | 2021-06-01..2021-07-30 | 76.1 | 147.8 | -71.7 | NOWY JASINIEC (10.8) | 250.1 | 243.4 | TORUŃ (39.8) |
| 040303_2.0002.189/13 | 2023-05-11..2023-07-09 | 69.4 | 83.2 | -13.8 | NOWY JASINIEC (10.8) | 259.3 | 254.1 | TORUŃ (39.8) |
| 040303_2.0002.189/13 | 2024-07-01..2024-08-29 | 126.9 | 187.7 | -60.8 | NOWY JASINIEC (10.8) | brak | brak | brak |
| 062006_2.0005.74 | 2018-05-01..2018-06-29 | 97.3 | 143.8 | -46.5 | ZAMOŚĆ (28.3) | brak | brak | brak |
| 062006_2.0005.74 | 2021-06-01..2021-07-30 | 167.9 | 120.6 | 47.3 | ZAMOŚĆ (28.3) | brak | brak | brak |
| 062006_2.0005.74 | 2023-05-11..2023-07-09 | 137.2 | 167.5 | -30.3 | ZAMOŚĆ (28.3) | brak | brak | brak |
| 062006_2.0005.74 | 2024-07-01..2024-08-29 | 276.2 | 137.0 | 139.2 | ZAMOŚĆ (28.3) | brak | brak | brak |
| 021701_2.0021.254/363 | 2018-05-01..2018-06-29 | 96.0 | 106.9 | -10.9 | BORÓW (4.9) | 260.3 | 236.1 | WROCŁAW-STRACHOWICE (28.7) |
| 021701_2.0021.254/363 | 2021-06-01..2021-07-30 | 112.7 | 141.0 | -28.3 | BORÓW (4.9) | 264.5 | 241.9 | WROCŁAW-STRACHOWICE (28.7) |
| 021701_2.0021.254/363 | 2023-05-11..2023-07-09 | 75.0 | 89.1 | -14.1 | BORÓW (4.9) | 253.4 | 231.3 | WROCŁAW-STRACHOWICE (28.7) |
| 021701_2.0021.254/363 | 2024-07-01..2024-08-29 | 199.8 | 189.6 | 10.2 | BORÓW (4.9) | brak | brak | brak |
| 280103_2.0059.352 | 2018-05-01..2018-06-29 | 93.0 | 99.4 | -6.4 | BARTOSZYCE (10.8) | 254.0 | 219.2 | KĘTRZYN (30.9) |
| 280103_2.0059.352 | 2021-06-01..2021-07-30 | 259.1 | 181.5 | 77.6 | BARTOSZYCE (10.8) | 259.7 | 236.5 | KĘTRZYN (30.9) |
| 280103_2.0059.352 | 2023-05-11..2023-07-09 | 61.2 | 90.6 | -29.4 | JUDYTY (14.2) | 240.6 | 225.6 | KĘTRZYN (30.9) |
| 280103_2.0059.352 | 2024-07-01..2024-08-29 | 184.6 | 171.8 | 12.8 | JUDYTY (14.2) | brak | brak | brak |

Opad: 16 okien, mediana bezwzględnej różnicy 29.4 mm, największa 139.2 mm; w 11 oknach NASA POWER dała więcej opadu niż posterunek.
ET0: 9 okien, IMGW minus NASA POWER od 5.2 do 34.8 mm, mediana 22.6 mm.
Dla działki 121406_2.0015.127 posterunki w promieniu 40 km nie miały pełnych 60 dni w żadnym z czterech okien.
