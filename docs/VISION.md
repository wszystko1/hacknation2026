# Bilans działki (nazwa robocza)

Raport wodny dla jednej działki ewidencyjnej, daty i uprawy. Działkę podaje się numerem albo klikiem na mapie. Bilans wody liczymy
definicją suszy z rozporządzenia MRiRW (Dz.U. 2019 poz. 739) i stawiamy obok progu dla tej uprawy i gleby. Ekran rolnika ma dwa
poziomy: u góry siedem rzeczy czytanych w trzy sekundy (werdykt zdaniem, jedna liczba jako dwa paski, działanie nr 1 z terminem,
pewność), pod strzałkami cała reszta. Widok doradcy zostaje pełny: wskaźniki, progi, źródła, niepewność, metoda. Pod werdyktem stoją
ocena SMSR IUNG dla gminy, trzy osobne odpowiedzi (werdykt, stan roślin z Sentinel-2 wobec porównywalnych sezonów działki, podatność
działki) ze zdaniem odczytu werdyktu i roślin naraz, bez jednej sklejonej liczby, i działania retencyjne z miejscem na zdjęciu. Każde
takie działanie wynika z łańcucha przyczyna → mechanizm → kandydat z geometrią → walidacja → działanie (rozdział „Łańcuch od przyczyny
do działania”); gdy teren nie pozwala wskazać miejsca, raport pokazuje działanie bez punktu na mapie i mówi dlaczego. Dalej
przyczyny, miejsca zatrzymania wody z formalnością z Prawa wodnego, zabiegi w uprawie, decyzja o nawadnianiu, plan z terminami i
prognoza przekroczenia progu do końca okresu krytycznego. Zgodność metody z SMSR i trafność prognozy są zmierzone i pokazane w
raporcie. Raport nie jest urzędowym stwierdzeniem suszy i mówi to zdaniem pod werdyktem. Ocenę bieżącą liczy rachunek i reguły, bez
uczenia maszynowego; prognoza w aplikacji nie ma zapisanych wag.

## Użytkownik i ból

- **Rolnik** z jedną lub kilkoma działkami, bez wiedzy o GIS i danych (zadanie, pkt 3.1). Mediana wieku pracującego użytkownika gospodarstwa
  51 lat (PSR 2020). eWniosekPlus samodzielnie wypełniło 27,6% użytkowników, 26,3% z pomocą doradcy ODR (badanie „Polska wieś i rolnictwo
  2023”), więc wielu czyta raport razem z doradcą.
- **Doradca ODR** albo osoba techniczna obok rolnika: widok „Doradca” tego samego raportu (wskaźniki, progi, źródła, niepewność, metoda).
- **Dziś:** SMSR IUNG ocenia suszę dla całej gminy, po zakończeniu okresu 6 dekad, w tabelach HTML, bez przyczyn i zaleceń dla działki.
  Pogoda, gleba, rzeźba terenu i rowy leżą w kilkunastu usługach (ULDK, IMGW, SoilGrids, NMT, BDOT10k). Czasu ręcznego składania tego
  dla jednej działki nie mierzyliśmy.
- **Skąd błędy:** gmina ma grunty czterech kategorii gleby, a ocena gminna nie mówi, która jest na działce; zalecenia są ogólne („rozważ
  międzyplony”), bez miejsca, terminu i formalności; rolnik nie wie, czy zastawka na rowie wymaga powiadomienia Wód Polskich.

## Test poniedziałku

Doradca wpisuje numer działki albo przybliża mapę i klika pole rolnika, potem wybiera datę i uprawę. Po kilku sekundach widzi bilans w mm
wobec progu z rozporządzenia dla tej gleby i uprawy, ocenę SMSR dla gminy i działanie retencyjne nr 1 z miejscem na zdjęciu; w ciągu 30 s
cały raport. PDF albo link z zapisanym planem idzie do rozmowy z rolnikiem, do spółki wodnej albo jako załącznik do powiadomienia Wód
Polskich: art. 395a ust. 2 Prawa wodnego wymaga m.in. numerów działek i współrzędnych miejsca robót, a raport je podaje. Pojęcia są te
same co w aplikacji suszowej (14 grup upraw, kategorie gleby I–IV, okres 6 dekad), ale o pomocy suszowej rozstrzyga ocena SMSR dla gminy,
nie ten raport. Przy każdym działaniu retencyjnym stoi formalność z cytatem przepisu albo „sprawdź w Wodach Polskich”.

## Ekran rolnika: dwa poziomy

Zasada: element znika z ekranu rolnika tylko wtedy, gdy ta sama informacja stoi w widoku doradcy, w README albo w `metrics.json`;
w przeciwnym razie trafia do rozwijanej części B. Widoku doradcy ta zmiana nie dotyczy (treść i układ bez zmian).

**Poziom A, góra ekranu, najwyżej 7 elementów:**
1. Nagłówek: działka, uprawa, data, gleba słowami („gleba bardzo lekka”, bez „kat. II”).
2. Werdykt jednym zdaniem z kolorem i słowem: „susza: tak” / „susza: nie” z dopiskiem „nasz szacunek”; poza sezonem szary „nie dotyczy”.
3. Jedna liczba jako dwa paski „zwykle X, teraz Y” dla głównej przyczyny pogodowej: pierwsza przyczyna z osi pogody (jedyna
   oś z rankingiem w mm: za mało opadu albo duże parowanie); gdy jej nie ma, tylko werdykt.
4. Co robić: działanie nr 1 z pinezką na mapie i kiedy (termin albo „termin podamy po wyliczeniu”). Gdy sekcja retencji nie ma jeszcze
   działania: „jeszcze nie liczymy”.
5. Pewność w 1–2 zdaniach: nasz szacunek wobec oceny IUNG dla gminy; „przy wniosku liczy się ocena IUNG”.
6. Przycisk „Raport PDF”.
7. Przycisk „Pokaż doradcy”.

**Poziom B, rozwijany, jedna strzałka na wiersz:** bilans (np. −201 mm) z progiem (−154 mm) w jednym miejscu, dlaczego (przyczyny
słowami), jak często ta działka cierpi (n z 10 lat), parowanie, stan roślin, plan z osią czasu, zabiegi w uprawie, formalności, „jak
policzyliśmy”, spadek słowami, gmina.

**Znika z ekranu rolnika:** powtórzenia tej samej liczby (zostaje jedno miejsce i rozwinięcie); zdanie „spadło 33 mm, o 74 mm mniej
niż zwykle” powtórzone pod działaniem; etykieta „bilans wody w 60 dniach”; czasy pobrania („14,5 s”, „razem 14,8 s”) i czasy per
źródło (zostają w widoku doradcy po rozwinięciu panelu źródeł); ramka „Brak: zgodność metody z oceną SMSR…”; „kat. II” (zostaje
kategoria słowami); ucięty wiersz gleby w panelu; kody „okres 4” i rzymskie daty (daty słowami; numeru okresu nie zaszywamy, wybór
okresu zmieni się osobno).

**Puste sekcje:** zamiast ramek „Brak: …” jedna linia na końcu raportu „Jeszcze nie liczymy: …”. Nie obiecujemy tego, czego nie ma.

**Panel „Skąd są dane” na mapie:** domyślnie jedna linia „✔ Dane: 10 z 10 źródeł · kopia z 21.11.2026 · Szczegóły” (czerwona tylko, gdy
brakuje źródła); rozwija się jako szuflada, nie jako nakładka na działkę; legenda nie zasłania działki; czasy tylko po rozwinięciu.

**Język działań:** „rozważ …” z warunkiem i następnym krokiem, nie rozkaz („zrób nieckę”, „zamontuj zastawkę”), bo lokalizacja i zgody
wymagają weryfikacji; efektu w mm nie obiecujemy. Opis „powyżej progu” brzmi jednoznacznie: „bilans jest lepszy niż próg suszy”.

## Złota ścieżka demo

Ekran startowy: z lewej mapa do wskazania działki (mapa podkładowa GUGiK, przy dużym przybliżeniu ortofotomapa), na niej ciemny pasek
wyboru z polem „Działka”. Ekran raportu ma trzy kolumny: pasek ikon 56 px (znak kropli, „Nowa ocena”, „Raport PDF”, „Zgodność
z SMSR”; bez awatara i konta), ortofotomapa 560 px (na ekranie węższym niż 1180 px 44% szerokości) i raport w całej pozostałej
szerokości, bo raport jest główną treścią. Mapa: biały obrys, przyciemnione otoczenie, strzałka kierunku spadku, dolny odcinek granicy,
rów i numery działań, nieruchoma przy przewijaniu, na niej ciemny pasek wyboru i zwinięty panel „Skąd są dane” (jedna linia, szuflada po rozwinięciu, legenda nie zasłania działki). Raport biały, werdykt raz na
górze, pod nim poziom B rozwijany strzałkami. Telefon (do 860 px): jedna kolumna, mapa nad raportem. W demo stoją liczby policzone przez aplikację. Dane demo to prawdziwe pobrania zamrożone
21.11.2026 w `demo/data/` (sceny nie wychodzą do sieci), w interfejsie z etykietą „kopia danych z 21.11.2026”.

Działka 1: `040303_2.0002.189/13` (gm. Dobrcz, 21,53 ha, staw przy granicy), „Zboża jare”. Datę wybieramy według SMSR, nie według naszego
wyniku: koniec okresu, w którym SMSR oznaczył w gminie Dobrcz w 2023 r. suszę dla zbóż jarych (roboczo 20.07.2023); jeśli nasz wynik
się różni, demo to pokazuje. Działka 2: `100403_2.0011.144` (gm. Góra Świętej Małgorzaty, 2,48 ha, rów przy granicy).

1. **Wskazanie na mapie** (scena „Wskazanie działki na mapie”): rolnik nie zna numeru. Scena przybliża okolice Dobrcza przyciskiem „+”
   i kółkiem myszy i klika pole; serwer zamienia punkt na działkę ewidencyjną (ULDK GetParcelByXY), mapa pokazuje biały obrys i kartę
   „Działka 189/13 · obręb Dobrcz · 21,53 ha” z przyciskami „To ta działka” i „Wskaż inną”. Scena kończy na karcie i sprawdza numer
   i powierzchnię. Klik poza Polską albo bez odpowiedzi ULDK: jedno zdanie przy mapie, pole numeru działa dalej.
2. **Wejście i zdjęcie** (scena „Działka z ewidencji na zdjęciu”): „To ta działka” wpisuje pełny identyfikator w pole „Działka” (numer
   można też wpisać), data, uprawa z listy alfabetycznej (14 grup, „Inna uprawa” na końcu; nad nią grupa „Podpowiedź z mapy upraw JRC
   2022”, gdy podpowiedź jest wiarygodna: warunek w „Modele i metody obliczeń”), „Oceń działkę”. Scena wybiera „Zboża jare” jak każdy
   użytkownik. Najpierw zdjęcie z obrysem, nagłówek „gm. Dobrcz › obręb Dobrcz”, 21,53 ha; panel źródeł liczy się w jednej linii, a stan i czas każdego źródła stoją po rozwinięciu szuflady. Klik na zdjęciu raportu poza obrysem pokazuje obrys i numer sąsiedniej działki z propozycją „Otwórz raport tej działki” (ta
   sama data i uprawa).
3. **Werdykt** (scena „Werdykt: bilans wobec progu z rozporządzenia”): góra ekranu to poziom A (sekcja „Ekran rolnika: dwa poziomy”):
   nagłówek, werdykt zdaniem (np. „Susza: tak, nasz szacunek” albo „Bilans jest lepszy niż próg suszy”), dwa paski „zwykle X, teraz Y”,
   działanie nr 1 z pinezką i terminem, zdanie o pewności z „przy wniosku liczy się ocena IUNG” i przyciski „Raport PDF” i „Pokaż
   doradcy”. Bilans w mm z progiem z Dz.U. 2019 poz. 739 stoi raz, w rozwijanym wierszu bilansu (pasek z kreską progu, opad P −
   parowanie E = bilans, dla tej gleby i uprawy), obok wiersza SMSR dla gminy z symbolem dla kategorii gleby, wiersza stanu roślin (z datą
   zdjęcia albo „ocena roślin w toku”), zdania odczytu werdyktu i roślin naraz i wiersza podatności („gdyby rosły tu zboża jare, …”).
   Stałe zdanie „To nie jest urzędowe stwierdzenie suszy; we wniosku liczy się ocena SMSR IUNG dla gminy” stoi pod werdyktem. Scena
   sprawdza zdanie werdyktu, zdanie zastrzeżenia, a po kliknięciu strzałki bilansu liczbę z progiem.
4. **Skrót** (scena „Cały raport w skrócie”): pod górą ekranu wiersze poziomu B z jedną liczbą albo słowem w tytule, każdy rozwija się
   strzałką; ramka zgodności z SMSR z `metrics.json` („przy takiej odległości od progu metoda zgadzała się z SMSR w K na 100
   przypadków; odpowiedź „zawsze częstsza odpowiedź” w T na 100”) stoi w wierszu „Jak policzyliśmy” i w widoku doradcy. Na końcu
   raportu jedna linia „Jeszcze nie liczymy: …”.
5. **Retencja i plan** (sceny „Gdzie zatrzymać wodę na działce”, „Plan działań: przełącznik „W planie””): klik w „Zatrzymanie wody”; nad
   działaniami lista rozpoznanych przyczyn z liczbami; mapa pokazuje strzałkę kierunku spadku ze spadkiem w %, dolny odcinek granicy
   z pasem trawy, rów i miejsca 1–3 rysowane z geometrii kandydata (linia pasa trawy albo miedzy, kierunek rzędów uprawy w poprzek stoku,
   punkt i obrys niecki) albo zdanie, że spadek jest za mały, by wskazać dolny odcinek; sekcja ma profil terenu, kartę kandydata
   (parametry jako zakresy ze źródłem, ryzyka, następny krok, pewność) i formalność z cytatem przepisu; działania brzmią „rozważ …” z warunkiem i następnym krokiem. Przełączenie działania na „W planie” zmienia licznik planu z N na N+1 na osi czasu do następnego okna suszy; nad osią stoi
   zdanie prognozy przekroczenia progu z jednym zdaniem jej trafności obok odpowiedzi trywialnej, z `metrics.json`.
6. **Trafność i źródła** (sceny „Zgodność z oceną państwa (SMSR)”, „Źródła, czasy i braki danych”, „Widok doradcy i raport PDF”): tabela
   2×2 z liczbą przypadków, pod nią trafność, trafność zrównoważona, czułość i precyzja dla suszy, każda obok wyniku odpowiedzi „zawsze
   częstsza odpowiedź”, liczba gmino-lat i częstość suszy w SMSR; źródła: na mapie jedna linia „✔ Dane: 10 z 10 źródeł · kopia z 21.11.2026 · Szczegóły”, po rozwinięciu szuflada z godziną, czasem
   i stanem każdego źródła, braki wprost; „Doradca” odsłania
   wejścia, niepewność oraz CSI, POD, FAR i Peirce wobec „zawsze susza” i klimatologii gminy; „Raport PDF” otwiera widok do druku.
7. **Data dzisiejsza** (scena „Raport na dziś: poza okresem monitoringu suszy”): działka 2, 21.11.2026, „Rośliny strączkowe”. Raport mówi
   „poza okresem monitoringu suszy (21.III–30.IX)”, werdykt i stan roślin mają status „nie dotyczy”, a w ich miejscu stoją wynik
   sezonu 2026, opad od 1.X wobec normy (odbudowa zapasu wody przed zimą) i działania, których termin wypada teraz (resztki pożniwne,
   zastawka przed roztopami); szansa na następny sezon jest nazwana klimatologią. Scena kończy na opadzie od 1.X i sprawdza jego liczbę.

Tytuły scen w `demo/scenes.py`, dokładnie i w tej kolejności (są też w `DONE.json`):
```
Wskazanie działki na mapie | Działka z ewidencji na zdjęciu | Werdykt: bilans wobec progu z rozporządzenia | Cały raport w skrócie
Gdzie zatrzymać wodę na działce | Plan działań: przełącznik „W planie” | Zgodność z oceną państwa (SMSR) | Źródła, czasy i braki danych
Widok doradcy i raport PDF | Raport na dziś: poza okresem monitoringu suszy
```

## Jak łączymy dane

Pięć kroków. Krok 2 daje trzy osobne odpowiedzi i nigdy nie skleja ich w jedną liczbę ani własny indeks.
1. **Wskaźniki.** Każdy stoi z liczbą, źródłem i stanem „jest” albo „brak” z powodem: opad i parowanie w oknie, kategoria gleby,
   spadek terenu, odległość rowu, NDVI i NDMI z datą zdjęcia, symbol SMSR gminy.
2. **Trzy odpowiedzi**, każda w swoim wierszu pod plakietką: (a) **werdykt** wzorem z rozporządzenia (sekcja 0); (b) **stan roślin**
   z satelity wobec porównywalnych sezonów działki: „słabsze”, „w normie” albo brak z powodem (rozdział „Stan roślin z satelity”);
   (c) **podatność**: jak często w 10 sezonach bilans spadał pod próg dla uprawy wybranej dziś (sekcja 1). Pod (a) i (b) jedno zdanie
   odczytu obu naraz; satelita nie zmienia bilansu ani plakietki:

| Werdykt | Rośliny | Zdanie odczytu |
|---|---|---|
| poniżej progu | słabsze | „susza potwierdzona przez stan roślin” |
| poniżej progu | w normie | „bilans poniżej progu; satelita jeszcze nie pokazuje stresu (wskaźnik reaguje z opóźnieniem)”, bez uspokajania |
| powyżej progu | słabsze | „spadek niewyjaśniony bilansem, sprawdź na polu (lokalny opad nawalny, zalanie, zbiór lub pokos, inna uprawa)” |
| powyżej progu | w normie | „brak oznak problemu z wodą” |
| dowolny | brak zdjęcia albo zdjęcie „nie ocenia stresu” | sam werdykt i zdanie, czego brakuje |

   Bez plakietki (okres jeszcze trwa, brak progu dla uprawy) zdania odczytu nie ma; oba wiersze stoją osobno.
3. **Przyczyny** (sekcja 3).
4. **Rekomendacje** z łańcucha przyczyna → mechanizm → kandydat → walidacja (rozdział „Łańcuch od przyczyny do działania”).
5. **Prognoza i termin:** szansa przekroczenia progu do końca okresu krytycznego nad osią planu (sekcja 6).

**Poza sezonem (od 1.X do 20.III, w tym dzień finału):** werdykt i stan roślin mają status „nie dotyczy”. W ich miejscu: podsumowanie
minionego sezonu (najgorszy okres, bilans wobec progu, ocena SMSR gminy), opad od 1.X do dnia oceny wobec mediany tych samych dni
w poprzednich latach z liczbą lat (odbudowa zapasu wody przed zimą) i działania, których termin wypada teraz, przed 21.III
(międzyplony, resztki pożniwne, zastawki przed roztopami). Szansę na następny sezon raport nazywa wprost klimatologią.

## Stan roślin z satelity

- **Scena:** Sentinel-2 L2A; chmury, cienie i śnieg zdejmuje maska SCL; obrys pomniejszony o 10 m od granicy (bez miedz, dróg
  i sąsiada); scena liczy się przy minimalnym udziale czystych pikseli obrysu (wartość w widoku doradcy). Od 25.01.2022 (baseline
  04.00) odejmujemy przesunięcie wartości o 1000. Raport podaje datę zdjęcia i zróżnicowanie NDVI w obrębie działki.
- **Płodozmian:** każdy miniony sezon działki dostaje grupę z krzywej NDVI prostymi regułami fenologii: ozime (zielone już w marcu,
  zbiór w lipcu), jare (ruszenie w kwietniu–maju, szczyt w czerwcu), późne / kukurydza (ruszenie w czerwcu, szczyt w sierpniu),
  trwałe użytki zielone (zielone cały sezon, pokosy z odrostem), goła gleba (NDVI niskie cały sezon). Bieżący stan porównujemy tylko
  z sezonami tej samej grupy i podajemy ich liczbę; przy mniej niż 3 takich sezonach raport pisze „za mało porównywalnych lat”.
  Sprawdzian reguł: mapy upraw JRC EUCROPMAP 2018 i 2022 w obrysie (`crop.rotation_agreement_jrc`). Progi reguł to propozycja zespołu.
- **Faza, nie kalendarz:** porównujemy według fazy rozwoju (dni od ruszenia wegetacji) albo szczytu NDVI sezonu, więc dojrzewanie
  zbóż ani późniejszy siew nie wyglądają jak susza. NDMI interpretujemy tylko przy zwartym łanie; przy odkrytej glebie mierzy glebę.
- **Zbiór i pokos:** gwałtowny spadek NDVI między kolejnymi zdjęciami oznacza zdjęcie „nie ocenia stresu”; nie wchodzi do odczytu (b).
- **W tle:** historia satelitarna (ok. 30 odczytów) liczy się po głównym raporcie i zostaje w pamięci podręcznej. Do tego czasu
  wiersz roślin, raport i PDF mówią wprost „ocena roślin w toku”.
- Rolnik czyta słowa („rośliny słabsze niż w 4 porównywalnych latach”), doradca NDVI, NDMI, grupę, liczbę sezonów, fazę i datę zdjęcia.

## Raport: sekcje w tej kolejności

Poniższe sekcje to treść poziomu B ekranu rolnika i widoku doradcy; góra ekranu rolnika (poziom A) jest opisana w „Ekran rolnika:
dwa poziomy”. Kolejność jak w zadaniu: ocena → przyczyny → retencja → agrotechnika → nawadnianie. Każda sekcja: wykres (SVG z serwera), pod nim 2–3
zdania (co pokazuje, dlaczego ważne, gdzie patrzeć), potem „Jak to policzono”. Tekst to stałe szablony z podstawionymi wartościami,
zalecenia wybierają reguły na wskaźnikach, model językowy nie bierze udziału w wyniku.

0. **Werdykt i ocena bieżąca.** KBW = Σ opadu − Σ parowania (ET0 FAO-56) w każdym z 14 okresów rozporządzenia (21.III–20.V …
   1.VIII–30.IX) zakończonych do daty analizy; okno kończy się na ostatniej pełnej dekadzie. Werdykt „Bilans poniżej progu suszy (szacunek dla działki)” (na ekranie rolnika zdanie z kolorem i słowem „susza: tak” / „susza: nie”, „nasz szacunek”; stan lepszy niż próg: „bilans jest lepszy niż próg suszy”), gdy w którymkolwiek okresie KBW < próg dla
   grupy uprawy i kategorii gleby; na górze okres z najmniejszym zapasem (KBW − próg). Pod plakietką stałe zdanie: „To nie jest urzędowe
   stwierdzenie suszy; we wniosku liczy się ocena SMSR IUNG dla gminy”. Przed 20.V: bilans od 21.III do końca ostatniej pełnej dekady,
   „okres jeszcze trwa”, bez plakietki. Od 1.X do 20.III: status „nie dotyczy” i treść z akapitu „Poza sezonem” (rozdział „Jak łączymy
   dane”). „Inna uprawa” i komórki „-”, „x” tabeli: sam bilans i zdanie, że rozporządzenie nie daje tu progu. Widok doradcy pokazuje
   obok drugi wariant werdyktu z parowaniem wzorem Doroszewskiego–Górskiego (sekcja „Modele i metody obliczeń”).
   - **Kategoria gleby** wybiera próg (zboża jare w okresie 1: kat. I −125 mm, kat. IV −194 mm). Odczyt warstwy IUNG
     `Susza:katgl_landuse2024` dla punktu, gdy działa; inaczej reguła z uziarnienia SoilGrids (sekcja „Modele i metody obliczeń”) ze
     zmierzoną zgodnością z mapą IUNG (`soil.category_agreement`). Gdy uziarnienie leży blisko granicy klas, raport podaje też wynik dla
     sąsiedniej kategorii. Doradca może kategorię poprawić.
   - **Wiersz SMSR:** symbol SMSR dla gminy, okresu, uprawy i kategorii gleby działki z tabeli dla roku daty analizy (jedna strona,
     ok. 0,14 s). Przed 2020 SMSR nie publikuje tabel gmin; raport to mówi.
   - **Wiersz satelity:** „Stan roślin na działce”: „słabsze” albo „w normie” wobec N sezonów tej samej grupy płodozmianu w tej samej
     fazie (rozdział „Stan roślin z satelity”), z datą zdjęcia; brak sceny bez chmur w 15 dniach przed datą, zdjęcie po zbiorze lub
     pokosie albo mniej niż 3 porównywalne sezony: „brak” z powodem; historia jeszcze się liczy: „ocena roślin w toku”. Pod nim zdanie
     odczytu werdyktu i roślin naraz z tabeli w rozdziale „Jak łączymy dane”.
   - **Wiersz podatności:** jedno zdanie z sekcji 1 („gdyby rosły tu zboża jare, bilans spadłby pod próg w k z 10 sezonów, najczęściej
     w lipcu, średnio o X mm”).
   - **Działanie nr 1:** najwyżej postawione działanie retencyjne z sekcji 4, z numerem na zdjęciu i formalnością, albo „brak miejsca na
     działce, bo …”.
1. **Podatność: 10 sezonów.** Pogoda działki z 10 sezonów i próg dla uprawy wybranej dziś, opisane wprost: „gdyby rosły tu zboża jare”.
   Słupek = najgorszy zapas sezonu, kreska = próg, liczba sezonów pod progiem; dla lat od 2020 znacznik oceny SMSR gminy. Rozbicie na
   miesiące okresu krytycznego uprawy (okres liczy się do miesiąca, w którym się kończy): w ilu sezonach pod progiem i średni niedobór
   w mm w tych sezonach. Do tego cechy samej działki: spadek terenu w % i reakcja NDVI działki w suche lata (o ile NDVI spadało wobec
   porównywalnych sezonów, gdy bilans był pod progiem; bez historii satelitarnej „brak” z powodem).
2. **Gmina i trafność metody.** Wynik SMSR gminy (symbol dla każdej kategorii gleby, udział powierzchni zagrożonej w %) obok wyniku działki,
   z przyczyną różnicy; zgodność według odległości od progu, tabela 2×2 i miary z sekcji „Pomiar zgodności z SMSR” z `metrics.json`.
3. **Przyczyny.** Każda przyczyna ma oś i dowód. Oś **pogody** (mało opadu, duże parowanie): wykres kaskadowy zwykły bilans tego okresu
   → mniej opadu → więcej parowania = wynik, z rankingiem w mm; to jedyna oś z rankingiem. Oś **miejsca** (spływ, gleba słabo trzyma
   wodę): gleba słowami IUNG („bardzo podatna na suszę”, kat. I), spadek i zlewnia z NMT, bez rankingu w mm. Oś **uprawy** (faza
   wrażliwa): przebieg NDVI i NDMI wobec mediany poprzednich sezonów. „Zwykły” opad i parowanie liczymy w dwóch definicjach: z roku
   o medianie bilansu i jako osobne mediany; etykieta „głównie opad” albo „głównie parowanie” stoi tylko, gdy obie się zgadzają, inaczej
   „oba czynniki”. Progi 85% i 110% bez zmian; etykieta nie zmienia się po usunięciu któregokolwiek z 9 wcześniejszych lat.
4. **Zatrzymanie wody.** Miejsce każdego działania wynika z łańcucha opisanego w rozdziale „Łańcuch od przyczyny do działania”; na
   mapie stoi tylko to, co ma geometrię kandydata. Model terenu (`app/advice/terrain_model.py`) daje płaszczyznę dopasowaną do wysokości
   w obrysie (średni spadek w %, kierunek spadku), zlewnię działki z flagą ucięcia przez siatkę, odcinek granicy, którym wypływa co
   najmniej 80% strumienia, najniższy punkt granicy i wnętrza, regiony zagłębień i najbliższy rów z BDOT10k z odległością w m.
   Geometrię mają cztery mechanizmy: pas trawy na odcinku wypływu (wzdłuż rowu, gdy rów biegnie przy nim), miedza w poprzek stoku,
   uprawa w poprzek stoku (obszar o spadku w progu i kierunek rzędów prostopadły do spadku, słowami „z północy na południe”) i niecka
   w zagłębieniu albo najniższym punkcie wnętrza. Pozostałe mechanizmy to „potencjał do weryfikacji” z powodem, bez punktu na mapie.
   Progi (najmniejszy spadek, odległość rowu od odcinka, spadek dla uprawy w poprzek stoku) są z poradnika CDR 2025 ze stroną; gdzie
   poradnik progu nie podaje (m.in. szerokości pasa, miedzy i oczka), parametr stoi jako zakres z materiału zagranicznego albo z poziomem
   „propozycja zespołu”. Gdy spadek płaszczyzny jest za mały, by wskazać dolny odcinek, raport pisze to wprost i nie rysuje strzałki.
   Gdy żaden mechanizm nie ma miejsca: „brak miejsca na działce, bo …” z niską pewnością. Akumulacja spływu i wilgotne strefy z satelity
   zastępują podstawę tylko tam, gdzie wygrały w sprawdzeniu miejsc (sekcja „Sprawdzenie miejsc retencji”); gdy wygra akumulacja, przy
   miejscu stoi też zlewnia w ha. Milimetrów ani m³ wody odpływającej z działki nie podajemy: współczynnik spływu nie ma źródła; efekt
   działania tylko jako zakres z literatury z dopiskiem „literatura”.
   Formalność z `app/advice/prawo_wodne.csv` (działanie, artykuł, cytat przepisu, strona PDF tekstu jednolitego Dz.U. 2026 poz. 1335,
   data sprawdzenia):
   - „nic nie trzeba”: zatrzymywanie wody w rowie (art. 395 pkt 11) i regulacja odpływu istniejącym urządzeniem na drenach (art. 395
     pkt 12), gdy skutek zostaje na własnym gruncie albo za pisemną zgodą sąsiadów;
   - „powiadomienie Wód Polskich”: przebudowa rowu w celu zatrzymania wody (art. 395 pkt 15 i art. 395a), w tym nowa zastawka na rowie;
     montaż regulatora na drenach to przebudowa obiektów drenarskich w celu hamowania odpływu (art. 395 pkt 16 i art. 395a);
   - „zgłoszenie”: staw do 5000 m² i 3 m głębokości, zasilany tylko opadem, roztopami lub wodą gruntową (art. 394 ust. 1 pkt 9);
   - „pozwolenie”: pobór ponad 5 m³/dobę średniorocznie (art. 34 pkt 12, art. 389 pkt 2);
   - „sprawdź w Wodach Polskich”, bez numeru artykułu: działanie, dla którego tekst ustawy nie rozstrzyga formalności.
   Granica art. 395 pkt 11 i pkt 15 nie jest zdefiniowana w ustawie; wpisy to interpretacja, w raporcie z dopiskiem „potwierdź
   w Wodach Polskich”. Przy każdym działaniu zmieniającym odpływ: art. 234 ust. 1 (bez szkody dla gruntów sąsiednich); rów poza działką: potrzebna pisemna
   zgoda sąsiada albo spółki wodnej. Przy zastawce ostrzeżenie: w mokrym okresie piętrzenie trzeba obniżyć, by nie zalać pola własnego
   ani sąsiada.
5. **Uprawa gleby.** Wykres: w ilu z 10 sezonów każda dekada IV–IX była pod progiem, pod nim kalendarz zabiegów do następnego okna suszy.
   Reguły: mulcz i resztki, międzyplon (na glebie bardzo lekkiej wymarzający), uprawa bez orki, w poprzek stoku, wcześniejszy siew lub forma
   ozima, porównanie grup upraw na tej glebie („zboża jare: pod progiem w 4 z 10 lat, zboża ozime: 1 z 10”, te same dane, inne progi).
6. **Plan i termin.** Oś czasu do następnego okna suszy (koniec ostatniego okresu z progiem dla grupy upraw) z działaniami z sekcji 4, 5
   i 7, przełącznik „W planie” przy każdym, licznik „N z M działań w planie”, stan w linku i w PDF. Nad osią zdanie prognozy przekroczenia
   progu do końca okresu krytycznego z jednym zdaniem trafności (sekcja „Prognoza przekroczenia progu”). Dla dat z przeszłości obok stoi
   „prognoza a co się stało”: bilans z archiwum w okresach kończących się po dacie oceny.
7. **Nawadnianie.** „Teraz tak / nie” z powodem (faza uprawy, woda w strefie korzeni wg FAO-56), dawka w mm i m³ na działkę (CDR 2025:
   20–25 mm na glebach lekkich, 30–35 mm na średnich), źródło wody z BDOT10k, pozwolenie powyżej 5 m³/dobę średniorocznie (art. 33 ust. 4
   pkt 1, art. 34 pkt 12).
8. **Źródła i ograniczenia.** Na ekranie rolnika bez czasów pobrania i czasów per źródło (zostają po rozwinięciu panelu i w widoku doradcy);
   braki to jedna linia „Jeszcze nie liczymy: …”. Źródło, co dało, godzina, czas, stan (jest / zapas / szacunek / brak / kopia z dnia), rozdzielczość; czego
   raport nie uwzględnia (drenowanie, wody gruntowe, faktyczna data siewu); źródło kategorii gleby i jej wpływ na wynik, odległość stacji.

## Modele i metody obliczeń

Ocena bieżąca nie używa uczenia maszynowego: każdą liczbę daje rachunek albo reguła, więc nie ma wag do uczenia ani wycieku danych.
- **Ocena bieżąca:** rachunek bilansu, opad minus parowanie w oknie 6 dekad kończącym się na ostatniej pełnej dekadzie, i porównanie
  z progiem z Dz.U. 2019 poz. 739 dla grupy uprawy i kategorii gleby. Parowanie dwoma wariantami: ET0 FAO-56 oraz wzór Doroszewskiego–
  Górskiego, którym liczy SMSR (Doroszewski i in. 2012, „Podstawy Systemu Monitoringu Suszy Rolniczej”, IUNG; postać wzoru, jednostki
  i współczynniki sprawdzamy w tym źródle i podajemy ze stroną), z temperatury i usłonecznienia ze stacji IMGW, które już pobieramy.
  Do werdyktu idzie FAO-56, dopóki liczby z pomiaru zgodności nie rozstrzygną inaczej („Otwarte decyzje”); drugi wariant stoi
  w widoku doradcy. Nawadnianie zostaje przy FAO-56.
- **Kategoria gleby:** reguła przypisująca uziarnienie 0–30 cm (piasek, pył, ił z SoilGrids) do kategorii I–IV, z sąsiednią kategorią
  przy granicy klas. Mapa IUNG, gdy odpowiada dla punktu, jest odczytem, nie modelem; na niej mierzymy zgodność reguły.
- **Roślinność:** grupa płodozmianu każdego sezonu z reguł fenologii na krzywej NDVI, potem odchylenie NDVI (NDMI tylko przy zwartym
  łanie) od sezonów tej samej grupy na tej samej działce w tej samej fazie rozwoju (własna historia działki, nie średnia regionu).
- **Podatność:** ten sam rachunek KBW na 10 sezonach pogody działki z progiem uprawy wybranej dziś, w podziale na miesiące okresu
  krytycznego.
- **Rozmieszczanie, podstawa:** płaszczyzna z = ax + by + c dopasowana metodą najmniejszych kwadratów do wysokości oczek siatki GUGiK
  w obrysie (10 m, wysokości co 0,1 m); średni spadek = 100 · √(a² + b²) %, kierunek spadku = kierunek wektora (−a, −b). Dolny odcinek
  granicy: ciągły fragment obrysu (punkty co krok siatki) z najniższymi wysokościami; najniższy punkt granicy i wnętrza; zagłębienie =
  oczko w obrysie niższe od wszystkich 8 sąsiadów; najbliższy rów z BDOT10k. Rachunek w numpy (działa w Windows), w jednym wymiennym
  module `app/advice/placement.py`.
- **Model terenu i zlewnia:** siatka zlewni (z marginesem ok. 300 m) jest pobierana w każdym raporcie, bez czytania `metrics.json`,
  i trafia do wejścia rozmieszczania. `app/advice/terrain_model.py` liczy z niej zlewnię działki w ha z flagą „ucięta przez siatkę”,
  odcinek granicy, którym wypływa co najmniej 80% strumienia (próg 80% to propozycja zespołu), i regiony zagłębień z głębokością;
  detektory (`app/advice/detectors.py`) czytają ten model. Wynik na syntetycznych terenach (stok 3%, płasko 0,3%, dolina z oczkiem)
  sprawdzają testy.
- **Rozmieszczanie, rozszerzenie (zastępuje podstawę tylko po wygranej w sprawdzeniu miejsc):** akumulacja spływu D8 (O'Callaghan i Mark 1984) na siatce
  z marginesem ok. 300 m wokół działki po wypełnieniu zagłębień, bo woda spływa od sąsiadów i do nich; punkt wypływu = oczko granicy
  z największą zlewnią w ha. Wilgotne strefy z satelity: mediana NDMI w każdym pikselu działki ze scen Sentinel-2 bez chmur z suchych
  okresów (okres rozporządzenia z bilansem działki poniżej mediany jej 10 sezonów; ta definicja to propozycja zespołu), z danych, które
  już pobieramy do wiersza satelity. Każdy wariant daje punkt wypływu i ocenę miejsca; który trafia do aplikacji, rozstrzyga pomiar.
- **Źródła metod:** najmniejsze kwadraty i kierunek spadku płaszczyzny to klasyczna geometria; akumulacja D8: O'Callaghan J.F.,
  Mark D.M. 1984, „The extraction of drainage networks from digital elevation data”, Computer Vision, Graphics, and Image Processing
  28(3), 323–344. README mówi: metody pochodzą z klasycznej literatury; patentu na nie nie znaleźliśmy (wyszukiwanie 21.11.2026).
- **Podpowiedź uprawy:** odczyt klas mapy upraw JRC EUCROPMAP 2022 (10 m) w obrysie. Wiarygodna, gdy jedna klasa pokrywa co najmniej
  połowę obrysu; wtedy 1–2 grupy rozporządzenia idą nad listę jako podpowiedź, bez wyboru za użytkownika. Mapa nie dzieli zbóż na ozime
  i jare, więc dla zbóż podpowiada obie grupy. Lista alfabetyczna pod podpowiedzią zostaje cała.
- **Prognoza przekroczenia progu:** dopełnianie bieżącego okna przebiegami pogody z wcześniejszych lat, bez zapisanych wag (niżej).

## Prognoza przekroczenia progu

Pytanie: jaka jest szansa, że w którymś okresie rozporządzenia kończącym się między datą oceny a końcem okresu krytycznego (ostatni
okres z progiem dla grupy upraw) KBW spadnie poniżej progu. Okresy zakończone przed datą oceny stoją już w werdykcie.
1. **W aplikacji: dopełnianie przebiegami.** Bilans do dnia oceny jest znany; resztę okresu dopełniamy pogodą z tych samych dni
   kalendarza w każdym wcześniejszym roku (20 lat ze stacji IMGW, dłużej z siatki NASA POWER), pierwsze 16 dni prognozą Open-Meteo, gdy
   jest. Wynik = odsetek przebiegów z przekroczeniem. Liczone na bieżąco z lat przed datą, bez zapisanych wag, więc bez wycieku z definicji.
   Dla daty z przeszłości rok analizy nie wchodzi do danych prognozy (ani do przebiegów, ani do częstości), a obok stoi „prognoza a co
   się stało” z archiwum: walidacja na jednym przypadku, którą rolnik widzi w raporcie.
2. **Punkt odniesienia: częstość historyczna:** odsetek wcześniejszych lat z przekroczeniem po tej dacie dla tej uprawy i gleby.
3. **Model do porównania:** drzewa wzmacniane gradientowo (LightGBM na procesorze; zapas: regresja logistyczna) na cechach: bilans do
   dnia oceny, dzień okna, kategoria gleby, uprawa, miesiąc, prognoza opadu na 16 dni. Zastępuje dopełnianie w aplikacji tylko, gdy na
   odłożonych latach pobije je i częstość historyczną (BSS wyższe o co najmniej 0,02, dolna granica 95% przedziału różnicy powyżej 0);
   inaczej porównanie trzech podejść idzie do README.
- **Walidacja krocząca:** centroidy 200 gmin z pomiaru zgodności, pogoda 2001–2025, daty oceny 1.V, 1.VI, 1.VII, 1.VIII; lata testowe
  2016–2025, rok Y liczony tylko z lat < Y (podział po latach, nie po oknach). Etykietę liczy ten sam kod KBW co werdykt. Gdzie nie ma
  archiwum prognoz 16 dni, główny wynik liczymy bez tej cechy.
- **Miara:** wynik Briera i BSS = 1 − BS / BS częstości historycznej (`forecast.brier_skill`, cel co najmniej 0,05), wykres kalibracji
  w 10 przedziałach, przedział 95% z bootstrapu po gmino-latach. `scripts/eval_forecast.py` (część `make eval`) zapisuje `forecast.*`.
- **W raporcie:** rolnik czyta „w k z n wcześniejszych lat dalsza pogoda doprowadziła do przekroczenia progu” i jedno zdanie trafności
  (trafność, czułość i precyzja dla przekroczenia przy szansie od 50%, obok odpowiedzi „zawsze częstsza odpowiedź”); doradca widzi metodę,
  Brier, BSS i kalibrację. Po końcu okresu krytycznego, a przed 1.X: „okres krytyczny dla tej uprawy już minął”; od 1.X do 20.III:
  częstość przekroczenia w następnym sezonie z wcześniejszych lat, nazwana w raporcie wprost klimatologią; „Inna uprawa”: brak
  progu, więc brak prognozy.

## Łańcuch od przyczyny do działania

Baza: 26 działań spisanych ze źródeł (11 retencji krajobrazowej, 11 glebowych i agrotechnicznych, 4 nawadniania; CDR 2025, katalog NWRM
Komisji Europejskiej, IUNG, FAO-56, załącznik organizatora) w katalogu CSV (`app/advice/catalog*.csv`). Kolumny: działanie, grupa,
mechanizm, przyczyny, warunki (każdy próg w osobnej kolumnie), parametry jako zakresy (od, do, jednostka, źródło albo „propozycja
zespołu”), efekt (od, do, jednostka), źródło (dokument, strona, dosłowny cytat, adres), poziom pewności (badanie / opinia ekspercka /
propozycja zespołu), formalność (artykuł), termin. Liczba trafia do raportu tylko z wypełnionym źródłem i cytatem; test to sprawdza.
Efekt działania tylko jako zakres z literatury, oznaczony „literatura”.

Pięć kroków, każdy w osobnym, małym module; wynik kroku 3 jest jedynym źródłem tekstu, mapy i PDF:
1. **Przyczyny** (`app/advice/diagnosis.py`): każda reguła, która zachodzi, daje przyczynę z osią (pogoda, miejsce, uprawa)
   i dowodem liczbowym. Nad działaniami stoi lista rozpoznanych przyczyn; ranking w mm tylko w osi pogody. Bez przyczyny nie ma zalecenia.
2. **Mechanizm** (`app/advice/mechanisms.py`, `mechanisms.csv`, 9 wierszy: pas trawy przy odcinku wypływu, pas buforowy wzdłuż rowu,
   miedza w poprzek stoku, uprawa w poprzek stoku, niecka, regulowany odpływ z drenów, ochrona zbiornika, przebudowa rowu,
   zadrzewienie śródpolne): jakie przyczyny adresuje, jakiego wejścia terenu wymaga, czy potrzebuje potrzeby, możliwości, czy obu.
   W sezonie mechanizm wchodzi do raportu, gdy jest **potrzeba** (z przyczyn) ORAZ **możliwość** (z terenu); poza sezonem wystarcza
   możliwość. Każdy `action_id` z obu katalogów ma mechanizm i detektor albo wpis „bez miejsca”.
3. **Kandydat** (`app/advice/detectors.py`, model terenu w `app/advice/terrain_model.py`): detektor mechanizmu zwraca `Candidate`:
   geometrię w EPSG:2180 (punkt, linia albo obrys) lub powód braku miejsca, parametry jako zakresy ze źródłem albo „propozycja
   zespołu”, dowód z terenu (spadek, zlewnia, odległość rowu, głębokość), pewność, ryzyka, formalność, zgody i następny krok. Geometrię
   mają cztery mechanizmy; reszta to „potencjał do weryfikacji” z powodem. Regulowany odpływ z drenów: o drenaż nie pytamy, zakładamy
   „nieznane”, więc to potencjał o niskiej pewności i zdaniu warunkowym.
4. **Walidacja** (`app/advice/validate.py`): zlewnia ucięta przez siatkę, zlewnia zewnętrzna większa niż 2–3 razy działka, miejsce
   bliżej niż 20 m od granicy, brak danych o drenażu, spadek poniżej rozdzielczości wysokości. Walidacja obniża pewność i dopisuje
   ryzyko; progi walidacji to propozycja zespołu i tak stoją w widoku doradcy.
5. **Działanie** (`retention_actions` w `app/advice/retention.py`; agrotechnika i nawadnianie z reguł katalogu): widok kandydata dla
   rolnika w formie „rozważ …, jeśli …; następny krok …” z liczbami tej działki, terminem i formalnością; efektu w mm nie obiecujemy.
   Zdanie o nowej zastawce mówi o odległości rowu („rów w odległości N m; połączenie spływu do potwierdzenia”), nie o linii spływu.
   `retention_actions` ustawia też pola mapy (spadek, kierunek spadku, dolny odcinek, wypływ), których wcześniej nikt nie ustawiał.

Warunki stosowania: działanie odpada, gdy nie pasuje do działki (głęboszowanie tylko na glebach średnich i ciężkich; regulowany odpływ
tylko na gruntach zdrenowanych o spadku do 1%, CDR 2025, mierzymy tu tylko potencjał; zastawka tylko na rowie przy odcinku wypływu).
Kolejność w grupie: wyżej działanie odpowiadające na więcej przyczyn naraz; dalej wykonalność w terminie od daty oceny i to, czy
rolnik zrobi je sam. Najwyżej 3 działania na grupę; grupy w kolejności zadania (retencja, agrotechnika, nawadnianie).
Progi bez strony w polskim źródle (np. odległość rowu od odcinka, wysokość piętrzenia, szerokość pasa) mają poziom pewności
„propozycja zespołu”; widok doradcy tak je opisuje.

## Pomiar zgodności z SMSR

Liczba z walidacji: **CSI wyniku „pod progiem / nad progiem” względem symboli SMSR IUNG**, z POD, FAR i wskaźnikiem Peirce'a
(POD − POFD); tabela 2×2 jak w weryfikacji prognoz, CSI = a/(a+b+c) pomija zgodne „brak”.
- Przypadek: gmina × rok × okres × grupa uprawy × kategoria gleby z symbolem „+” lub „-” w tabelach SMSR („x”, „#”, „*”, „n” pomijamy).
- Niezależność: KBW jest jeden dla gminy, roku i okresu; symbole 14 grup i 4 kategorii to ten sam bilans z różnymi progami, a kolejne
  okresy dzielą 50 z 60 dni. Wielkość próby podajemy więc w gmino-latach testowych (`smsr.n_gmina_years`, cel co najmniej 300), liczbę
  symboli obok, a bootstrap losuje gminy.
- Zbiór: ok. 200 gmin losowanych warstwowo po 16 województwach, lata 2020–2026 (`scripts/fetch_smsr.py` → `data/raw/smsr/`, ok. 16 min).
  Podział z góry: 50 gmin do wyboru wzoru parowania, 150 do testu liczonego raz. Nasz wynik liczy ten sam kod co aplikacja
  (`fetch_weather` dla centroidu gminy, KBW, progi z rozporządzenia), z tą samą kolejnością źródeł pogody.
- **Dwa wzory parowania:** `scripts/eval_smsr.py` liczy każdą miarę dla obu wariantów werdyktu i zapisuje ją z przyrostkiem
  (`smsr.*_fao56`, `smsr.*_dg`); klucze bez przyrostka to wariant, którego używa aplikacja (FAO-56 do rozstrzygnięcia). Okno obu
  kończy się na ostatniej pełnej dekadzie. README pokazuje oba warianty na gminach testowych.
- **Korekta względem IUNG (warunkowa):** tylko gdy pomiar pokaże systematyczną różnicę (przedział 95% z bootstrapu po gminach dla
  stosunku liczby naszych „pod progiem” do liczby „+” SMSR nie obejmuje 1). Wtedy najpierw jedno przesunięcie progu w mm dobrane na
  latach 2020–2025 i sprawdzone na 2026 (`smsr.threshold_shift_mm`, `smsr.balanced_accuracy_2026` bez i `_shifted` z przesunięciem).
  Wchodzi do aplikacji tylko, gdy poprawia 2026; README i linia „Jak to policzono” nazywają je dopasowaniem do IUNG, nie progiem
  z rozporządzenia.
- Linie odniesienia: „zawsze brak” (CSI 0); „zawsze susza” (CSI równe częstości „+”, w latach takich jak 2026 wysokie); klimatologia
  gminy (susza, gdy w pozostałych latach 2020–2026 ta sama gmina, uprawa, kategoria i okres miały „+” w co najmniej połowie lat; widzi też
  lata późniejsze, więc sprzyja linii odniesienia); ten sam kod na samej siatce NASA POWER zamiast stacji IMGW.
- Dowód, że metoda odróżnia się od odpowiedzi trywialnej: `smsr.csi_gain_vs_baseline` = CSI metody − większe z CSI „zawsze susza”
  i klimatologii gminy, cel co najmniej 0,10. Częstość „+” (`smsr.base_rate`) stoi w raporcie i README obok CSI.
- Do tego przedział 95% z bootstrapu po gminach, zgodność w koszykach odległości od progu (0–10, 10–25, 25–50, >50 mm; z nich zdanie
  w ramce zgodności). `scripts/eval_smsr.py` (`make eval`) zapisuje klucze `smsr.*` w `metrics.json`.
- Miary dla rolnika (widok rolnika i raport): trafność (`smsr.accuracy`), trafność zrównoważona (`smsr.balanced_accuracy`), czułość
  (`smsr.recall`) i precyzja (`smsr.precision`) dla suszy, zawsze obok wyniku odpowiedzi „zawsze częstsza odpowiedź”
  (`smsr.accuracy_majority`; jej trafność zrównoważona to 0,5). CSI, POD, FAR, Peirce, Brier i BSS z kalibracją stoją w README i w
  widoku doradcy, każda z objaśnieniem jednym zdaniem.
- Pomocnicze: `soil.category_agreement` (reguła gleby wobec mapy IUNG w ok. 100 punktach); z testu 50 losowych działek z 16 województw
  (daty historyczne, poza sezonem i dzisiejsza): `retention.place_or_reason_share`, `retention.with_place_share` (działanie retencyjne
  z miejscem albo jawne „brak miejsca, bo …”), `robustness.report_ok_under_30s_share`, `robustness.p50_s`, `robustness.p95_s`.

## Sprawdzenie miejsc retencji

`scripts/eval_retention.py` (`make eval`), obok `retention.place_or_reason_share`. Przed automatyzacją ręczne sprawdzenie na ok. 10
działkach na ortofotomapie, ze zrzutami ekranu. Pomiar rozstrzyga, czy rozszerzenie zastępuje podstawę.
- **Rowy (punkt wypływu):** ok. 50 działek z rowem BDOT10k do 50 m od granicy; odsetek działek, w których punkt wypływu leży do 30 m
  od rowu, dla podstawy, czyli najniższego punktu granicy (`retention.outlet_hit_lowest`), akumulacji D8 (`retention.outlet_hit_d8`),
  najwilgotniejszego punktu granicy z mediany NDMI (`retention.outlet_hit_ndmi`) i 100 losowych punktów granicy
  (`retention.outlet_hit_random`); wynik wariantu, którego używa aplikacja: `retention.outlet_hit_share`. Rów jest zagłębieniem
  w modelu terenu, więc wynik jest optymistyczny; README to mówi.
- **Zbiorniki (miejsce niecki):** zbiorniki i oczka z BDOT10k w promieniu ok. 1 km od działek; AUC oceny miejsca w zbiornikach wobec
  losowych miejsc dla podstawy, czyli głębokości pod płaszczyzną dopasowaną w oknie ok. 100 m wokół miejsca
  (`retention.pond_auc_lowest`), akumulacji D8 (`retention.pond_auc_d8`) i mediany NDMI bez pikseli samej wody
  (`retention.pond_auc_ndmi`); wynik wariantu aplikacji: `retention.pond_auc`.
- **Wybór:** punkt wypływu (pas trawy, zastawka) bierze wariant z najwyższym wynikiem testu rowów, miejsce niecki wariant z najwyższym
  AUC; przy remisie zostaje podstawa, potem akumulacja. Tabela wszystkich wariantów w README.

## Odrębność

Typowe rozwiązanie tego zadania, jakiego się spodziewamy: mapa, NDVI, semafor „ryzyko wysokie” z własnego indeksu, porady z modelu językowego
albo z szablonu bez warunku, bez walidacji. Forma jest podobna (mapa + raport), różnica jest sprawdzalna: bilans definicją prawną suszy
w mm wobec progu, który zna każdy, kto składał wniosek suszowy, obok oceny SMSR dla gminy; zmierzona zgodność z oceną państwa na co
najmniej 300 gmino-latach dla dwóch wzorów parowania, porównana z odpowiedziami trywialnymi; trzy osobne odpowiedzi (werdykt,
rośliny wobec sezonów tej samej grupy płodozmianu w tej samej fazie, podatność) zamiast jednego semafora; prognoza przekroczenia progu sprawdzona na odłożonych latach wobec
częstości historycznej; zalecenie z przyczyn i warunku, retencyjne z miejscem z geometrii działki (płaszczyzna spadku, dolny odcinek
granicy, zagłębienia, rów) sprawdzonym wobec rowów i zbiorników z BDOT10k obok losowych punktów, akumulacja spływu i wilgotne strefy
z satelity tylko po wygranej, formalność z cytatem przepisu; ten sam numer i data dają zawsze ten sam raport; braki
danych wprost; działanie sprawdzone na 50 losowych działkach, także z datą listopadową.

## Dane

Źródła, licencje, rozmiary i daty: `docs/DANE.md`. Pobieranie dla działki jest napisane i zmierzone (10 źródeł, każde ze stanem, czasem i
adresem; 10 działek: 6,1 s typowo, 8,7 s najgorzej, 10 ms z pamięci podręcznej) i leży w `app/geodata` z testami. Działka z punktu na
mapie: ULDK GetParcelByXY; kafle mapy: mapa podkładowa i ortofotomapa GUGiK. Pogoda: Open-Meteo, a gdy odmawia, posterunki IMGW + ET0
FAO-56 ze stacji synoptycznej, luki z NASA POWER; temperatura i usłonecznienie z tej samej stacji IMGW zasilają też wzór
Doroszewskiego–Górskiego. Sentinel-2 L2A z warstwą SCL: bieżące zdjęcie od razu, historia sezonów w tle. Dochodzą: tabele gmin SMSR IUNG (wiersz gminy na żywo, archiwum do pomiaru), kategoria
gleby z warstwy IUNG, progi z Dz.U. 2019 poz. 739 w CSV z testem, katalog działań (CDR 2025, NWRM), formalności Prawa wodnego
w CSV z cytatami, siatka wysokości GUGiK w obrysie (z marginesem ok. 300 m, pobierana w każdym raporcie: zlewnia, odcinek wypływu), rowy, zbiorniki i oczka z BDOT10k do testu miejsc, pogoda 2001–2026 dla centroidów 200 gmin (2020–2026 do pomiaru zgodności, 2001–2025 do walidacji prognozy), prognoza 16 dni
Open-Meteo, mapy upraw JRC EUCROPMAP 2018 i 2022 czytane oknem w obrysie (podpowiedź uprawy, sprawdzian grup płodozmianu). Danych syntetycznych w produkcie nie ma; dane demo to prawdziwe
pobrania z datą, oznaczone w interfejsie.

## Czego NIE budujemy

1. Modelu językowego piszącego raport lub zalecenia; czatu z „agronomem AI”.
2. Logowania, kont, danych osobowych (numer działki z ULDK nie wskazuje właściciela).
3. Rozpoznawania uprawy siecią neuronową (zostaje podpowiedź z mapy JRC) ani „działki bliźniaka” z zabiegów sąsiadów (brak danych).
4. Kroku „sprawdź dane przed zapisem”, osobnej aplikacji mobilnej, PDF składanego w LaTeX (PDF to wydruk strony).
5. Mapy z biblioteką (Leaflet, OpenLayers) ani z CDN; przeglądarka nie łączy się z serwerami GUGiK. Mapa wskazania to nasz krótki skrypt
   na kaflach podawanych przez nasz serwer; mapa raportu to zdjęcie działki z serwera z nakładką SVG.
6. Własnego indeksu suszy, kosztorysów bez źródła cen, prognozy sezonowej Open-Meteo (183 dni) w widoku rolnika, uczenia maszynowego
   w ocenie bieżącej, sieci neuronowych (PyTorch) do prognozy.
7. Plakietki „Susza rolnicza” ani zastosowania raportu jako dowodu we wniosku suszowym.
8. Milimetrów ani m³ wody odpływającej z działki; zostaje miejsce, kierunek spływu i powierzchnia zlewni (otwarta decyzja). Efektów
   działań bez źródła z cytatem.
9. Metod, progów ani tekstu ACPF (USDA); bibliotek hydrologicznych bez działającej wersji dla Windows: geometrię i spływ liczymy
   w numpy.
10. Pytania do rolnika o drenaż ani innych pól formularza dla łańcucha przyczyn; ekranu rolnika (poziomy A i B) i widoku doradcy
    nie przebudowujemy: karta kandydata to dodatkowy częściowy szablon.
11. Niczego innego z listy „Otwarte decyzje”, dopóki nie zapadnie decyzja.

## Moduły krytyczne dla jury

Małe, typowane, z testami i opisem w `docs/PYTANIA_JURY.md`:
1. `app/drought/kbw.py` + `app/drought/progi_dz_u_2019_739.csv`: 14 okresów, KBW, próg, wynik, stany „poza okresem” i „brak progu”,
   okno do ostatniej pełnej dekady, parowanie FAO-56 albo Doroszewskiego–Górskiego za jednym parametrem; test porównuje CSV
   (14 grup × 4 kategorie × 14 okresów) z rozporządzeniem, a współczynniki wzoru D–G z cytatem źródła.
2. `app/advice/rules.py` + `app/advice/catalog*.csv` + `app/advice/prawo_wodne.csv`: reguła = przyczyny i warunek na wskaźnikach →
   szablon zdania, liczby, termin, źródło, formalność; kolejność po liczbie przyczyn, wykonalności i tym, czy rolnik zrobi to sam. Testy:
   każde działanie ma w CSV artykuł, cytat, stronę PDF i datę sprawdzenia albo „sprawdź w Wodach Polskich” bez numeru artykułu; liczba
   efektu tylko z cytatem źródła; próg z polskiego źródła ze stroną albo z poziomem „propozycja zespołu”. Progi bez źródła w widoku
   doradcy opisane jako propozycje zespołu.
3. `app/advice/terrain_model.py`, `app/advice/detectors.py`, `app/advice/mechanisms.py`, `app/advice/validate.py` (łańcuch przyczyna →
   mechanizm → kandydat → walidacja, rozdział „Łańcuch od przyczyny do działania”): `Candidate` z geometrią albo powodem braku miejsca,
   parametrami jako zakresy ze źródłem, ryzykami i następnym krokiem; testy: każdy `action_id` ma mechanizm, detektory na syntetycznych
   terenach, walidacje, test łańcucha na trzech syntetycznych terenach (każde działanie ma mechanizm, każdy kod przyczyny jest w diagnozie,
   jest geometria albo powód, zdanie bez niewypełnionych pól).
3a. `app/advice/placement.py`: płaszczyzna najmniejszych kwadratów (spadek, kierunek), dolny odcinek granicy, najniższe punkty,
   zagłębienia, rów i z nich miejsca działań albo „brak miejsca, bo …”; rozszerzenie (akumulacja D8, mediana NDMI) za tym samym
   interfejsem, wybierane wynikiem sprawdzenia miejsc. Typowane wejście (obrys, siatka wysokości, wody z BDOT10k) i wyjście (lista
   miejsc z rodzajem, położeniem, długością albo kierunkiem i powodem); moduł da się wymienić bez zmian w reszcie raportu.
4. `app/validation/agreement.py`: tabela 2×2, trafność, trafność zrównoważona, czułość, precyzja, CSI, POD, FAR, Peirce, linie
   odniesienia, bootstrap po gminach; wołany przez `scripts/eval_smsr.py`.
5. `app/forecast/exceedance.py`: częstość historyczna, dopełnianie przebiegami i model za jednym typowanym interfejsem, stany „ok”,
   „okres minął”, „brak progu”, klimatologia poza sezonem; podział po latach i miary (Brier, BSS, kalibracja) w
   `scripts/eval_forecast.py`; test, że rok Y nie widzi lat ≥ Y.
6. `app/crop_condition/`: grupa płodozmianu z krzywej NDVI, porównanie w fazie rozwoju tylko z sezonami tej samej grupy (co najmniej 3),
   oznaczenie zbioru lub pokosu, odczyt werdykt × rośliny jako tabela pięciu zdań; satelita nie zmienia werdyktu.

## Stos

Szablon bez zmian: FastAPI + Jinja + HTMX, Python 3.12, uv; z warstwy danych httpx, numpy, pyproj, rasterio (gotowe pakiety dla Windows);
do porównania prognozy LightGBM (gotowe pakiety dla Windows, procesor). Wykresy i mapa raportu to SVG z serwera. Mapa wskazania: nasz
skrypt bez bibliotek (przesuwanie, przybliżanie przyciskami +/− i kółkiem, klik → długość i szerokość geograficzna → `/api/dzialka` → ULDK
GetParcelByXY); kafle mapy podkładowej i ortofotomapy pobiera z WMS/WMTS GUGiK nasz serwer, z pamięcią podręczną na dysku; kafle i
odpowiedzi ULDK dla okolic obu działek demo leżą w `demo/data/`, więc test i scena działają bez sieci. Bez bibliotek JS i CDN. Części
raportu dochodzą przez odpytywanie HTMX (co ok. 1 s) o fragmenty liczone, gdy ich źródło jest gotowe; pobrane dane w pamięci podręcznej na
dysku. Uruchomienie bez `make`: `uv run python -m app` (port `HN_PORT`, domyślnie 8000), także w Windows. PDF: styl do druku; przykładowe
raporty do zgłoszenia robi `scripts/export_reports.py` (Playwright, `page.pdf`). Bez PyTorcha i karty graficznej.

## Ryzyka i plan B

| Ryzyko | Plan B |
|---|---|
| Referencja jury nie jest liczona metodą IUNG | pytanie do mentorów jako pierwsze; rdzeń `kbw.py` wymienny, reszta raportu bez zmian |
| Urzędnik czyta wynik jako urzędowe stwierdzenie suszy | plakietka „Bilans poniżej progu suszy (szacunek dla działki)”, stałe zdanie o SMSR, wiersz SMSR gminy tuż pod spodem |
| Kategoria gleby z SoilGrids rozjeżdża się z mapą IUNG | warstwa IUNG pierwsza; zgodność reguły zmierzona; wynik dla sąsiedniej kategorii; doradca poprawia |
| Warstwa IUNG nie odpowiada dla punktu | kategoria z obrazu mapy WMS (kolor legendy) w 100 punktach do pomiaru zgodności; w aplikacji reguła z SoilGrids |
| IUNG liczy ewapotranspirację innym wzorem niż FAO-56 | oba warianty (FAO-56, Doroszewski–Górski) w pomiarze zgodności; wybór po liczbach z 50 gmin rozwojowych; przy systematycznej różnicy jedno przesunięcie progu sprawdzone na 2026 |
| Źródło wzoru Doroszewskiego–Górskiego niedostępne albo niejednoznaczne | wariant D–G nie wchodzi; FAO-56 zostaje, raport i README mówią, czego nie sprawdziliśmy |
| Za mało sezonów tej samej grupy płodozmianu albo reguły fenologii mylą grupę | „za mało porównywalnych lat” zamiast porównania; sprawdzian na mapach JRC 2018 i 2022 w README |
| Historia satelitarna liczy się dłużej niż raport | raport i PDF mówią „ocena roślin w toku”; werdykt i podatność nie czekają |
| Opad ze stacji i z siatki różni się w oknie 60 dni typowo o 29 mm | pytanie do mentora; kolejność źródeł bez zmian do odpowiedzi; CSI na samej siatce jako linia odniesienia |
| Błędny numer artykułu Prawa wodnego | CSV z cytatem, stroną i datą sprawdzenia; test; bez potwierdzonego przepisu „sprawdź w Wodach Polskich” |
| Open-Meteo archiwum odrzuca limitem dziennym | łańcuch IMGW + NASA POWER, pamięć podręczna, dostawca i odległość stacji w raporcie |
| SMSR ogranicza pobieranie archiwum | przerwy 0,5 s, mniejsza próba z podanym N; 84 strony już sparsowane |
| Satelita lub NMT przekracza limit czasu | nie blokują bilansu; wiersz mówi „brak” i dlaczego; historia satelity dociąga się w tle |
| Ani akumulacja spływu, ani wilgotne strefy z satelity nie biją podstawy w sprawdzeniu miejsc | aplikacja zostaje przy podstawie; porównanie wszystkich wariantów w README |
| Siatka z marginesem 300 m przekracza limit punktów lub czasu | poza działką co 20–30 m; zlewnia przycięta do marginesu, raport to mówi; podstawa marginesu nie potrzebuje |
| Wysokości co 0,1 m dają płaskie fragmenty i fałszywe zagłębienia | płaszczyzna ze wszystkich oczek obrysu uśrednia zaokrąglenia; za mały spadek: zdanie zamiast dolnego odcinka; test zbiorników mierzy, czy zagłębienia trafiają |
| Zlewnia ucięta przez siatkę, zlewnia zewnętrzna wielokrotnie większa od działki albo miejsce przy granicy | walidacja obniża pewność kandydata i dopisuje ryzyko; flaga „ucięta” stoi w karcie i w widoku doradcy |
| Brak danych o drenażu | nie pytamy; regulowany odpływ z drenów to potencjał o niskiej pewności ze zdaniem warunkowym |
| Granica art. 395 pkt 11 i 15 Prawa wodnego niejednoznaczna | cytat dosłowny, strona PDF, dopisek „potwierdź w Wodach Polskich”; bez potwierdzenia „sprawdź w Wodach Polskich” |
| Szerokości pasa, miedzy i oczka bez polskiego źródła (CDR 2025 ich nie podaje) | zakres z materiału zagranicznego z nazwą źródła albo „propozycja zespołu”, nigdy „norma” |
| Poradnik CDR 2025 nie podaje progu reguły rozmieszczania | próg w katalogu z poziomem „propozycja zespołu”, widok doradcy to mówi; pytanie do mentora |
| Prognoza nie bije punktów odniesienia | model nie wchodzi do aplikacji (porównanie w README); gdy i dopełnianie przegrywa z częstością historyczną, raport podaje samą częstość i mówi to wprost |
| Mapa JRC myli uprawę na działce | podpowiedź tylko przy pokryciu ≥ 50% obrysu, nigdy wybór za użytkownika; pierwsza do cięcia |
| L1 nie stoi o 20:00 | kolejność cięcia z „Drabiny cięć”; lista „Nigdy nie tniemy” zostaje |
| Jury poda numer w innym formacie albo nie zna numeru | pełny identyfikator, obręb + numer (ULDK GetParcelByIdOrNr z listą), współrzędne, klik na mapie startowej (ULDK GetParcelByXY) |
| Kafle GUGiK albo ULDK GetParcelByXY nie odpowiadają w czasie pokazu | kafle i odpowiedzi ULDK dla okolic działek demo zamrożone w `demo/data/`; pole numeru działa bez mapy; zdanie przy mapie mówi, co się stało |

## Otwarte decyzje

Punktów z tej listy na razie nie budujemy; nie mają pracy w planie, dopóki decyzja nie zapadnie.
- **Milimetry wody odpływającej z działki** (jako przedział albo wcale). Raport podaje miejsce, kierunek spływu i udział powierzchni.
- **Jedna liczba na slajd:** zgodność z SMSR, czas odpowiedzi czy trafność prognozy. Mierzymy i pokazujemy w raporcie wszystkie trzy.
- **Wariant ekranu z drugiej rundy makiet;** do decyzji obowiązuje kierunek wizualny z `docs/DESIGN.md`.
- **Hosting:** publiczny link (konto w usłudze hostingowej, ok. 7 USD miesięcznie, do 3 godzin pracy) czy tylko instrukcja w README.
- **Wzór parowania w werdykcie:** FAO-56 czy Doroszewski–Górski; rozstrzygnięcie po liczbach `smsr.*_fao56` i `smsr.*_dg`. Do tego
  czasu werdykt liczy FAO-56, a widok doradcy pokazuje drugi wariant (to budujemy).
- **Źródło opadu:** stacja czy siatka (różnica w oknie 60 dni typowo 29 mm, najwięcej 139 mm, może zmienić werdykt); pytanie do mentora.
- **Progi bez źródła w poradniku CDR 2025** (odległość rowu od dolnego odcinka, najmniejszy spadek, wysokość piętrzenia, warunki
  agrotechniki): od mentorów; do tego czasu propozycje zespołu. Reguły z tymi progami budujemy.
- Czym jest referencja jury i w jakim formacie poda numer działki (pytania do mentorów); nazwa produktu.

## Drabina cięć

- **L0:** opis, zrzuty, tabela progów i metoda w README.
- **Szkielet (sob 16:30):** `app/geodata` z testami; `app/drought/kbw.py` z CSV progów; wynik i widok do druku dla dowolnej działki
  i daty. W tle od razu: `scripts/fetch_smsr.py` (ok. 16 min) i pogoda 2001–2026 dla 200 gmin. Pierwsze 20 min: odczyt warstwy IUNG
  `Susza:katgl_landuse2024` dla 10 działek z pomiaru czasu.
- **L1 (sob 20:00):** dowolna działka i data, także listopadowa: wejście numerem albo klikiem na mapie startowej (przybliżanie, ULDK
  GetParcelByXY, obrys i numer do potwierdzenia „To ta działka” / „Wskaż inną”), klik w sąsiednią działkę na zdjęciu raportu z propozycją
  przejścia, zdjęcie z obrysem, werdykt z wykresem bilansu, plakietką i zastrzeżeniem, wiersz SMSR gminy dla daty analizy, wiersz stanu
  roślin z satelity, działania retencyjne z podstawy rozmieszczania (płaszczyzna spadku, dolny odcinek granicy, najniższe punkty,
  zagłębienia, najbliższy rów z BDOT10k; pas trawy, uprawa w poprzek stoku, niecka, zastawka) z formalnością z CSV, agrotechnika
  i nawadnianie jako zdania z reguł, skrót, źródła i braki, widok do druku; ekran raportu: pasek ikon 56 px, mapa 560 px, reszta raport; ekran rolnika w dwóch poziomach (A: 7 elementów, B: rozwijane
  wiersze), panel „Skąd są dane” zwinięty do jednej linii, działania w języku „rozważ …”.
- **L2 (ndz 02:00):** `smsr.*` w `metrics.json` z miarami dla rolnika i sekcja gminy, 10 sezonów i lista przyczyn, sprawdzenie miejsc
  na rowach i zbiornikach (podstawa wobec akumulacji D8 z marginesem 300 m, mediany NDMI z suchych okresów i losowych punktów) z wariantem
  zwycięskim w aplikacji, cytat O'Callaghan i Mark 1984 i zdanie o patencie w README, katalog działań CSV ze źródłami i kolejnością po
  liczbie przyczyn, wykresy agrotechniki i nawadniania, plan z przełącznikami i osią czasu, `soil.category_agreement`, test 50 działek
  z `retention.*` i `robustness.*`, przełącznik Rolnik / Doradca, prognoza dopełnianiem przebiegami nad osią planu z `forecast.*`
  z walidacji kroczącej, bez roku analizy w danych, z „prognoza a co się stało”. Trzy osobne odpowiedzi ze zdaniem odczytu werdykt ×
  rośliny; stan roślin z maską SCL, marginesem 10 m, grupami płodozmianu, fazą rozwoju, oznaczeniem zbioru lub pokosu i historią
  w tle („ocena roślin w toku”); podatność w miesiącach okresu krytycznego ze średnim niedoborem w mm, spadkiem i reakcją NDVI;
  treść poza sezonem (status „nie dotyczy”, opad od 1.X wobec normy, działania z terminem teraz, klimatologia); okno do ostatniej
  pełnej dekady, wariant Doroszewskiego–Górskiego w widoku doradcy i `smsr.*_fao56`, `smsr.*_dg`.
- **L3 (ndz 09:00, potem bez nowych funkcji):** model prognozy w aplikacji, jeśli wygrał; podpowiedź uprawy z mapy JRC; pełny widok
  doradcy; bilans FAO-56 w nawadnianiu; układ na telefon; wyszukiwanie po nazwie obrębu; dopracowanie wyglądu; korekta
  względem IUNG, jeśli pomiar pokaże systematyczną różnicę; sprawdzian grup płodozmianu na mapach JRC 2018 i 2022.
- **Łańcuch przyczyna → działanie (nd, po ekranie rolnika):** każdy etap zostawia aplikację uruchamialną i widoczną zmianę w raporcie.
  Cięcie w tej kolejności: test łańcucha na demo i jego scena → detektor uprawy w poprzek stoku → walidacje inne niż zlewnia ucięta
  i płaskość (zostają te dwie) → karta kandydata w wierszu rozwijanym (zostaje zdanie „rozważ …” z geometrią na mapie).
  Zostają zawsze: oś przyczyny, mechanizmy z CSV, `Candidate` jako źródło tekstu i mapy, cytaty prawa.
- **Kolejność cięcia:** podpowiedź uprawy → sprawdzian płodozmianu na mapach JRC (grupy zostają) → korekta względem IUNG
  (zostaje próg z rozporządzenia) → reakcja NDVI w suche lata w podatności → wilgotne strefy z satelity (zostają podstawa i akumulacja) → test zbiorników
  (`retention.pond_auc`; niecka zostaje w najniższym punkcie albo zagłębieniu) → model prognozy w aplikacji (zostaje dopełnianie,
  porównanie w README) → akumulacja spływu i siatka z marginesem 300 m (zostaje podstawa z L1, test rowów z najniższym i losowymi
  punktami w README) → bilans FAO-56 w nawadnianiu (zostaje prosta decyzja) → wykres gminy w sekcji 2 (wiersz SMSR zostaje) → stan planu w linku i PDF (przełącznik
  w raporcie należy do złotej ścieżki i zostaje).
- **Nigdy nie tniemy:** poziomu A ekranu rolnika (7 elementów, bez czasów pobrania i bez „kat. II”, „okres 4”), złotej ścieżki, wskazania działki na mapie (obowiązkowy zakres zadania, pkt 3.3 ppkt 2), liczby zgodności z SMSR,
  wiersza SMSR gminy i zdania zastrzeżenia pod werdyktem, trzech osobnych odpowiedzi bez jednej sklejonej liczby, działania retencyjnego
  nr 1 z miejscem, daty poza okresem monitoringu, jawnych braków danych, działania dla dowolnej działki.

## Historia zmian

- K0 (krytyka wizji): krok „Szkielet”; miary `smsr.csi_gain_vs_baseline ≥ 0,10` i `smsr.n_gmina_years ≥ 300`; warstwa IUNG przed
  regułą z SoilGrids; plakietka „(szacunek dla działki)” ze zdaniem o SMSR; działanie nr 1 na pierwszym ekranie; wiersz stanu roślin;
  `prawo_wodne.csv` z cytatami; bez objętości odpływu, awatara i liczb agronomicznych bez źródła.
- sob 16:15, W01: realizujemy tylko punkty ustalone i nieoznaczone, więc prognoza przekroczenia progu z miarami i modułem
  `app/forecast/exceedance.py`, podpowiedź JRC na liście upraw, milimetry odpływu, wybór liczby na slajd, kolejność cięć i hosting
  przeszły do „Otwarte decyzje”, a rozdziały „Modele i metody obliczeń” i „Skąd biorą się rekomendacje” opisują ocenę bez uczenia
  maszynowego i 5 kroków od bazy 26 działań do zdania; żaden test akceptacyjny nie został usunięty (powód: nie podany).
- sob 16:24, W02 (zastępuje W01): do otwartych decyzji przechodzi tylko punkt o milimetrach wody odpływającej z działki, a wracają
  i obowiązują prognoza przekroczenia progu dopełnianiem przebiegami (bez zapisanych wag, walidacja krocząca po latach, Brier i BSS
  wobec częstości historycznej, model tylko po wygranej), podpowiedź uprawy z mapy JRC nad listą alfabetyczną i kolejność cięć; K3
  znów ma czek `forecast.brier_skill ≥ 0,05`, doszedł test `tests/acceptance/test_exceedance_forecast.py` (xfail do zbudowania), żaden
  test nie został usunięty (powód: W01 objęła za dużo, właściciel miał na myśli tylko punkt o spływie).
- sob 17:29, W03: działkę można wskazać klikiem na mapie startowej (mapa podkładowa i ortofotomapa GUGiK z przybliżaniem, bez bibliotek
  z CDN, ULDK GetParcelByXY, obrys i numer do potwierdzenia „To ta działka” / „Wskaż inną”), a klik w sąsiednią działkę na zdjęciu
  raportu proponuje przejście do niej; doszła scena „Wskazanie działki na mapie” na początku złotej ścieżki, czek tej sceny i testu
  `tests/acceptance/test_map_pick.py` (xfail do zbudowania) w K4, punkt w L1 i na liście „Nigdy nie tniemy”; żaden test nie został
  usunięty (powód: zadanie wymienia wskazanie działki na mapie w obowiązkowym zakresie prototypu, pkt 3.2 i 3.3 ppkt 2, a jury może
  tak zacząć).
- sob 19:44, W04: miejsca retencji liczy analiza spływu na siatce z marginesem 300 m (wypełnienie zagłębień, spływ wielokierunkowy
  zamiast D8, zlewnia w ha, metoda ACPF), sprawdzona testem wypływu wobec rowów i zbiorników, z najniższym punktem granicy jako
  zapasem; wszystkie przyczyny naraz z kolejnością po liczbie przyczyn i najwyżej 3 działaniami na grupę; katalog CSV ze źródłem,
  cytatem i poziomem pewności; nowa zastawka to powiadomienie Wód Polskich (art. 395a) z ostrzeżeniem o mokrym okresie; rolnik widzi
  trafność, trafność zrównoważoną, czułość i precyzję obok „zawsze częstsza odpowiedź”, CSI i BSS zostają dla doradcy i README;
  doszły testy `tests/acceptance/test_runoff_placement.py`, `test_action_catalog.py`, `test_measures.py` (xfail do zbudowania),
  w `test_water_law.py` zmieniona oczekiwana formalność `zastawka-nowa`, żaden test nie został usunięty (powód: woda spływa od sąsiadów
  i do nich, a D8 na wysokościach zaokrąglonych do 0,1 m rozstrzyga remisy przypadkowo).
- sob 20:00, W05: progi rozmieszczania są z podręcznika ACPF v7.0 w jednostkach metrycznych ze stroną w katalogu (rów zadarniony
  z SPI = ln(SCA · tan β) powyżej progu i odcinka min. 50 m, pasy konturowe przy nachyleniu 4–15%, drenaż kontrolowany przy ok. 1%
  lub mniej), zagłębienia głębsze niż ok. 0,2 m zostają, akumulację liczą D8 i D-nieskończoność, a metodę wypływu (D8,
  D-nieskończoność albo najniższy punkt granicy) wybiera test rowów, wewnątrz działki siatka 5 m w limicie; README cytuje Tomer i in.
  2013, 2015 i podręcznik v7.0, kodu ani tekstu ACPF nie kopiujemy; w `tests/acceptance/test_runoff_placement.py` test zagłębień
  zastąpiony testem płytkich i głębokich zagłębień, test wyboru metody wypływu rozszerzony o D8 i D-nieskończoność, rodzaj
  „pas zadarniony” to teraz „rów zadarniony”, doszły testy SPI, rowu zadarnionego ≥ 50 m, pasów konturowych i cytatów w README,
  w `test_action_catalog.py` test progów ACPF ze stroną; żaden test nie został usunięty (powód: ACPF liczy D8 na modelu 1–2 m,
  u nas siatka 10 m z wysokościami co 0,1 m, więc metodę wybieramy pomiarem, a progi bierzemy ze źródła zamiast własnych).
- sob 20:29, W06: miejsca działań retencyjnych liczy podstawa z geometrii działki bez ACPF (płaszczyzna najmniejszych kwadratów ze
  spadkiem i kierunkiem, dolny odcinek granicy, najniższe punkty, zagłębienia, najbliższy rów; pas trawy, uprawa w poprzek stoku, niecka,
  zastawka), a akumulacja D8 (O'Callaghan i Mark 1984) i mediana NDMI z suchych okresów zastępują ją tylko po wygranej w teście rowów
  i zbiorników; progi z poradnika CDR 2025 albo jako propozycja zespołu; README ze zdaniem o klasycznej literaturze i patencie; ekran
  raportu: pasek ikon 56 px, mapa 560 px (44% na węższym ekranie), reszta raport; w `tests/acceptance/test_runoff_placement.py`
  usunięte testy płytkich i głębokich zagłębień, SPI, rowu zadarnionego, pasów konturowych, zastawki przy linii spływu, pasa i niecki
  przy wypływie, sortowania po zlewni, liczby zastawek i wyboru D8 / D-nieskończoności, doszły testy płaszczyzny, dolnego odcinka,
  zastawki przy dolnym odcinku, zagłębień, niecki, uprawy w poprzek stoku, płaskiej działki, wyboru wariantu w obu testach i README
  bez ACPF; w `test_action_catalog.py` test progów ACPF zastąpiony testem progów z polskiego źródła albo propozycji zespołu; doszedł
  `tests/acceptance/test_report_layout.py` (xfail do zbudowania) (powód przy ACPF: nie podany; przy układzie: mapa zajmowała za dużo
  ekranu, a raport jest główną treścią).
- sob 21:24, W07: nowy rozdział „Jak łączymy dane” (wskaźniki ze stanem, trzy osobne odpowiedzi: werdykt, stan roślin, podatność,
  ze zdaniem odczytu werdykt × rośliny z tabeli pięciu przypadków), poza sezonem status „nie dotyczy” z opadem od 1.X wobec normy,
  działaniami z terminem teraz i klimatologią, stan roślin z grupami płodozmianu, fazą rozwoju, maską SCL, marginesem 10 m,
  oznaczeniem zbioru lub pokosu i historią w tle („ocena roślin w toku”), podatność „gdyby rosły” w miesiącach okresu krytycznego,
  werdykt w dwóch wariantach parowania (FAO-56 w werdykcie, Doroszewski–Górski w widoku doradcy, `smsr.*_fao56` i `smsr.*_dg`),
  okno do ostatniej pełnej dekady, warunkowe przesunięcie progu względem IUNG i prognoza bez roku analizy z „prognoza a co się
  stało”; przyczyn ta zmiana nie dotyczy; w `tests/acceptance/test_crop_condition.py` usunięte testy mediany tej samej dekady
  (`test_drier_than_usual_in_plain_words_with_values_for_the_advisor`, `test_as_usual_when_close_to_the_median`,
  `test_no_history_is_a_stated_gap`, `test_july_cereals_drop_is_read_as_ripening_not_drought`, `test_no_clear_scene_is_a_stated_gap`
  w starej postaci) i zastąpione testami grup, fazy, zwartego łanu, zbioru, jakości sceny i oceny w toku; w
  `test_exceedance_forecast.py` test „okres minął” przeszedł na 15.09.2023, a data dzisiejsza daje klimatologię; doszły
  `test_three_answers.py`, `test_off_season.py`, `test_vulnerability.py`, `test_evaporation_formula.py` (xfail do zbudowania)
  (powód: krytyczna recenzja wizji; zmiana przyczyn będzie osobna).
- nd 01:41, W08: ekran rolnika ma dwa poziomy (góra: najwyżej 7 elementów — nagłówek, werdykt zdaniem, dwa paski „zwykle / teraz”, działanie nr 1 z terminem, pewność, „Raport PDF” i „Pokaż doradcy”; reszta w wierszach rozwijanych), znikają powtórzenia liczb, czasy pobrania, „kat. II”, „okres 4”, rzymskie daty i ramki „Brak: …” (zamiast nich linia „Jeszcze nie liczymy: …”), panel „Skąd są dane” jest zwinięty do jednej linii, a działania brzmią „rozważ …”; widok doradcy bez zmian; dodany `tests/acceptance/test_farmer_screen.py` (xfail do zbudowania), żaden test nie został usunięty (powód: ekran rolnika miał za dużo elementów i powtórzeń, badanie interfejsu zatwierdzone przez właściciela 22.11).
- nd 02:00, W09: działania retencyjne wynikają z łańcucha przyczyna (oś pogoda / miejsce / uprawa, ranking w mm tylko dla pogody) → mechanizm (9 wierszy `mechanisms.csv`, w sezonie potrzeba ORAZ możliwość) → kandydat z geometrią (pas trawy, miedza, uprawa w poprzek stoku, niecka; reszta „potencjał do weryfikacji”, bez miejsca „brak miejsca na działce, bo …” z niską pewnością) → walidacja (zlewnia ucięta, zlewnia zewnętrzna, granica, drenaż, rozdzielczość) → działanie „rozważ …, jeśli …; następny krok …”, a regulator drenów to art. 395 pkt 16 i 395a (regulacja istniejącego urządzenia: pkt 12), przebudowa rowu pkt 15; w `tests/acceptance/test_water_law.py` oczekiwanie dla `dreny-regulowany-odplyw` zmienione z „nic nie trzeba, art. 395 pkt 12” na „powiadomienie Wód Polskich, art. 395 pkt 16”, doszedł `tests/acceptance/test_cause_chain.py` (xfail do zbudowania), żaden test nie został usunięty (powód: przyczyny i działania łączył tylko tekst, a mapa nie miała danych o spadku i spływie).
