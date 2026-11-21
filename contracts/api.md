# HTTP API

Wszystkie trasy GET. Parametry raportu (te same we wszystkich trasach raportu):

| Parametr | Wymagany | Wartość |
|---|---|---|
| `dzialka` | tak | pełny identyfikator działki, np. `040303_2.0002.189/13` |
| `data` | tak | data oceny `RRRR-MM-DD`, od `2016-01-01` do dziś |
| `uprawa` | tak | kod `CropGroup` (`zboza_jare`, `rosliny_straczkowe`, …, `inna`); lista: `/api/uprawy` |
| `widok` | nie | `rolnik` (domyślnie) albo `doradca` |
| `plan` | nie | numery działań w planie, np. `1,3,4` |
| `gleba` | nie | kategoria gleby ustawiona przez doradcę: `I`, `II`, `III`, `IV` |

| Trasa | Odpowiedź |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /` | ekran startowy: pasek wyboru (Działka, Data oceny, Uprawa, „Oceń działkę”), przykładowe działki |
| `GET /raport?…` | raport HTML: mapa z lewej, raport z prawej. Błędne pola: 422 i ekran startowy z błędem przy polu |
| `GET /raport/druk?…` | ten sam raport w jednej kolumnie (widok do druku, PDF przez `window.print()`) |
| `GET /raport/sekcja/{id}?…` | fragment HTML jednej sekcji (`historia`, `gmina`, `przyczyny`, `retencja`, `uprawa`, `plan`, `nawadnianie`, `zrodla`) do odpytywania HTMX; 404 dla innego `id` |
| `GET /raport/zdjecie?dzialka=…&data=…` | JPEG ortofotomapy działki (ten sam, na którym leży nakładka `MapView`) |
| `GET /api/uprawy` | `[{"kod": "burak_cukrowy", "nazwa": "Burak cukrowy"}, …]`, 15 pozycji, „Inna uprawa” na końcu |
| `GET /api/raport?…` | `Report` jako JSON (`app/models.py`); przykład: `contracts/examples/raport_dobrcz_2023-07-20.json` |
| `GET /api/dzialka?lon=…&lat=…` | działka ewidencyjna zawierająca punkt WGS84 (ULDK GetParcelByXY): `{"dzialka": "040303_2.0002.189/13", "numer": "189/13", "obreb": "Dobrcz", "gmina": "Dobrcz", "pow_ha": 21.53, "obrys_4326": [[[lon, lat], …]]}` |
| `GET /mapa/kafel/{warstwa}/{z}/{x}/{y}.jpg` | kafel 256×256 px w siatce Web Mercator (XYZ) pobrany przez serwer z WMS/WMTS GUGiK; `warstwa` = `podklad` (mapa podkładowa) albo `orto` (ortofotomapa); pamięć podręczna na dysku; bez sieci i bez kafla w kopii: 200 i jednolity kafel zastępczy (nie 404, żeby przeglądarka nie zapisała błędu w konsoli) |

Błędy wejścia w `/api/raport`: 422 i `{"bledy": [{"field": "dzialka", "message": "Numer ma postać 040303_2.0002.189/13"}]}`.
Pola: `dzialka`, `data`, `uprawa`, `gleba`. Działka nieznana w ULDK albo niedostępna: 422 z błędem pola `dzialka`.

Błędy w `/api/dzialka`: 422 i `{"bledy": [{"field": "dzialka", "message": "…"}]}` dla braku `lon` albo `lat`, wartości
niebędących liczbą, punktu poza Polską, punktu bez działki i braku odpowiedzi ULDK. Bez sieci (`GEODATA_OFFLINE=1`) odpowiada
kopia z `demo/data/map/`: obrysy działek demo i ich sąsiadów (punkt w obrysie), punkt spoza kopii daje 422.

Dane działki: `app/datasource.load(parcel_id, day)` zwraca kopię z `demo/data/geodata/` (dokładna data albo późniejsza
kopia przycięta do daty), inaczej pobiera na żywo przez `app.geodata.fetch_all` (pamięć podręczna `data/raw/geodata_cache`,
`GEODATA_OFFLINE=1` = tylko pamięć podręczna).
