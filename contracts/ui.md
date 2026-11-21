# Elementy strony, na których opierają się sceny i testy

Te identyfikatory i atrybuty zostają przy każdej zmianie wyglądu (sceny w `demo/steps/` i testy ich szukają).

| Selektor | Gdzie | Co zawiera |
|---|---|---|
| `#f-dzialka`, `#f-data`, `#f-uprawa`, przycisk „Oceń działkę” | pasek wyboru `.pick` | trzy pola i akcja; błąd: `aria-invalid="true"` i `.field-error#e-<pole>` |
| `.report-head`, `.crumb`, `.sub`, `h1` | nagłówek raportu | „gm. Dobrcz › obręb Dobrcz”, „21,53 ha”, „Działka 189/13” |
| `.map img`, `.map svg` | kolumna mapy | zdjęcie i nakładka w tej samej przestrzeni pikseli |
| `.ledger .sources li` | karta „Skąd są dane” | wiersz na źródło; `is-done` / `is-fallback` / `is-missing` / `is-waiting` |
| `#werdykt`, `#plakietka`, `.big-number`, `.verdict-sentence`, `#zastrzezenie` | sekcja 0 | werdykt, liczba w mm, zdanie, stałe zastrzeżenie |
| `#poza-sezonem` | sekcja 0 | baner „Poza okresem monitoringu suszy (21.III–30.IX)” |
| `#wiersz-smsr`, `#wiersz-satelita`, `#dzialanie-1` | `dl.facts` pod werdyktem | ocena SMSR gminy, stan roślin, działanie nr 1 |
| `#skrot`, `#zgodnosc-ramka`, `#skrot li a` | „Cały raport w skrócie” | ramka zgodności i 8 wierszy z linkiem `#<id sekcji>` |
| `#historia` … `#zrodla` | sekcje 1–8 | `section` z `id` równym `SectionId` |
| `[data-plan-switch]` | przełącznik „W planie” przy działaniu | `input type=checkbox`, `value` = numer działania |
| `[data-plan-count]`, `#licznik-planu` | sekcja 6 | licznik „N z M działań w planie” |
| `[data-plan-item]` | oś czasu sekcji 6 | pozycja planu, klasa `is-planned` |
| `#tabela-2x2`, `#gmina .nums` | sekcja 2 | tabela 2×2 i CSI, POD, FAR, liczba gmino-lat |
| `#tabela-zrodel` | sekcja 8 | źródło, co dało, pobrano, czas, stan |
| `.seg a` „Rolnik” / „Doradca”, `body.view-doradca`, `.advisor` | nagłówek | przełącznik widoku i bloki doradcy |
| `#pdf`, `#druk-info` | nagłówek / widok do druku | „Raport PDF” otwiera `/raport/druk` z tym samym planem |
