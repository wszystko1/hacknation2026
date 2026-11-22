# ChrońPlon: scenariusz demo

Demo jedzie na kopii danych dwóch działek z 21.11.2026 (`demo/data/`), bez sieci. Każda scena kończy się na ekranie, który nazywa jej
tytuł. Uruchomienie: `make demo`; wideo powstaje z tych samych scen (`demo/scenes.py`).

1. **Wskazanie działki na mapie.** Mapa startowa, przybliżenie, klik w pole. Karta pokazuje numer 189/13, obręb Dobrcz i 21,53 ha;
   „To ta działka” potwierdza obrys. Kafle podaje serwer aplikacji, przeglądarka nie łączy się z GUGiK.
2. **Działka z ewidencji na zdjęciu.** Obrys na ortofotomapie i raport w prawej części ekranu.
3. **Werdykt: bilans wobec progu z rozporządzenia.** Bilans działki, próg z Dz.U. 2019 poz. 739 dla zbóż jarych, ocena na 20.07.2023.
4. **Cały raport w skrócie.** Najwyżej 7 wierszy skrótu; rozwijany wiersz otwiera liczby, przyczyny i plan.
5. **Gdzie zatrzymać wodę na działce.** Działanie nr 1 z numerem na zdjęciu (punkt wypływu), jako kandydatura do weryfikacji w terenie.
6. **Plan działań: przełącznik „W planie”.** Dodanie działania do planu, termin.
7. **Zgodność z oceną państwa (SMSR).** Odpowiedź obok SMSR dla gminy i zdanie trafności.
8. **Źródła, czasy i braki danych.** Tabela źródeł z czasem pobrania.
9. **Widok doradcy i raport PDF.** Pełne liczby i raport PDF do pobrania; miary zgodności są w zakładce Wiarygodność.
10. **Raport na dziś: poza okresem monitoringu suszy.** Raport dla bieżącej daty poza okresem, z planem.

Liczby do powiedzenia na scenie 7 (z `metrics.json`): przy bilansie co najmniej 25 mm poniżej progu SMSR potwierdza suszę w 92,3%
przypadków, przy marginesie do 10 mm to 55,2%, czyli rzut monetą. Zdanie pod werdyktem: „To nie jest urzędowe stwierdzenie suszy.
Urzędową ocenę suszy w gminie publikuje IUNG (SMSR).”

Czego demo nie pokazuje: działania na żywo dla dowolnej działki (jest kopia danych dwóch działek) i pomiaru czasu raportu na 20 działkach
(w toku). Zrzuty ekranu: `docs/img/`.
