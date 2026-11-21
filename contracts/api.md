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

Błędy wejścia w `/api/raport`: 422 i `{"bledy": [{"field": "dzialka", "message": "Numer ma postać 040303_2.0002.189/13"}]}`.
Pola: `dzialka`, `data`, `uprawa`, `gleba`. Działka nieznana w ULDK albo niedostępna: 422 z błędem pola `dzialka`.

Dane działki: `app/datasource.load(parcel_id, day)` zwraca kopię z `demo/data/geodata/` (dokładna data albo późniejsza
kopia przycięta do daty), inaczej pobiera na żywo przez `app.geodata.fetch_all` (pamięć podręczna `data/raw/geodata_cache`,
`GEODATA_OFFLINE=1` = tylko pamięć podręczna).
