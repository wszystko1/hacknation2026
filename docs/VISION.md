# Bilans działki (nazwa robocza)

Raport wodny dla jednej działki ewidencyjnej, daty i uprawy. Działkę podaje się numerem albo klikiem na mapie. Bilans wody liczymy
definicją suszy z rozporządzenia MRiRW (Dz.U. 2019 poz. 739) i stawiamy obok progu dla tej uprawy i gleby. Pod nim stoją ocena SMSR IUNG
dla gminy, stan roślin z Sentinel-2 i pierwsze działanie retencyjne z miejscem na zdjęciu. Dalej przyczyny, miejsca zatrzymania wody z
formalnością z Prawa wodnego, zabiegi w uprawie, decyzja o nawadnianiu, plan z terminami i prognoza przekroczenia progu do końca okresu
krytycznego. Zgodność metody z SMSR i trafność prognozy są zmierzone i pokazane w raporcie. Raport nie jest urzędowym stwierdzeniem suszy
i mówi to zdaniem pod werdyktem. Ocenę bieżącą liczy rachunek i reguły, bez uczenia maszynowego; prognoza w aplikacji nie ma zapisanych
wag.

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

## Złota ścieżka demo

Ekran startowy: z lewej mapa do wskazania działki (mapa podkładowa GUGiK, przy dużym przybliżeniu ortofotomapa), na niej ciemny pasek
wyboru z polem „Działka”. Ekran raportu: z lewej ortofotomapa z białym obrysem, przyciemnionym otoczeniem, punktem wypływu, rowem i
numerami działań, nieruchoma przy przewijaniu, na niej ciemny pasek wyboru i karta „Skąd są dane”; z prawej biały raport, werdykt raz na
górze, pod nim „Cały raport w skrócie”. W demo stoją liczby policzone przez aplikację. Dane demo to prawdziwe pobrania zamrożone
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
   użytkownik. Najpierw zdjęcie z obrysem, nagłówek „gm. Dobrcz › obręb Dobrcz”, 21,53 ha; karta źródeł wypełnia się wierszami ze stanem i
   czasem. Klik na zdjęciu raportu poza obrysem pokazuje obrys i numer sąsiedniej działki z propozycją „Otwórz raport tej działki” (ta
   sama data i uprawa).
3. **Werdykt** (scena „Werdykt: bilans wobec progu z rozporządzenia”): plakietka „Bilans poniżej progu suszy (szacunek dla działki)” albo
   „Bilans powyżej progu suszy (szacunek dla działki)”, bilans w mm jako największy element, zdanie „W tych 60 dniach wyparowało o X mm
   więcej wody, niż spadło. To Y mm poniżej progu suszy dla zbóż jarych na tej glebie”, pasek z kreską progu, linia „opad P − parowanie E
   = bilans (okres nn, dd.mm–dd.mm) · próg z Dz.U. 2019 poz. 739” i stałe zdanie „To nie jest urzędowe stwierdzenie suszy; we wniosku
   liczy się ocena SMSR IUNG dla gminy”. Pod nim wiersz „Ocena SMSR dla gminy Dobrcz w tym okresie” z symbolem dla kategorii gleby
   działki, wiersz stanu roślin z satelity i działanie nr 1 z numerem na zdjęciu. Scena sprawdza tekst plakietki, zdanie zastrzeżenia
   i wartość z wiersza SMSR.
4. **Skrót** (scena „Cały raport w skrócie”): ramka zgodności („przy takiej odległości od progu metoda zgadzała się z SMSR w K na 100
   przypadków; odpowiedź „zawsze częstsza odpowiedź” w T na 100”, z `metrics.json`), pod nią 8 wierszy z liczbą (sekcje 1–8 poniżej),
   każdy przewija do swojej sekcji.
5. **Retencja i plan** (sceny „Gdzie zatrzymać wodę na działce”, „Plan działań: przełącznik „W planie””): klik w „Zatrzymanie wody”; nad
   działaniami lista rozpoznanych przyczyn z liczbami; mapa pokazuje linie spływu skoncentrowanego, punkt wypływu z powierzchnią zlewni
   w ha, rów i miejsca 1–3 (albo zdanie, że spadek jest za mały, by wskazać linię spływu); sekcja ma profil terenu i formalność z cytatem
   przepisu. Przełączenie działania na „W planie” zmienia licznik planu z N na N+1 na osi czasu do następnego okna suszy; nad osią stoi
   zdanie prognozy przekroczenia progu z jednym zdaniem jej trafności obok odpowiedzi trywialnej, z `metrics.json`.
6. **Trafność i źródła** (sceny „Zgodność z oceną państwa (SMSR)”, „Źródła, czasy i braki danych”, „Widok doradcy i raport PDF”): tabela
   2×2 z liczbą przypadków, pod nią trafność, trafność zrównoważona, czułość i precyzja dla suszy, każda obok wyniku odpowiedzi „zawsze
   częstsza odpowiedź”, liczba gmino-lat i częstość suszy w SMSR; źródła z godziną, czasem i stanem, braki wprost; „Doradca” odsłania
   wejścia, niepewność oraz CSI, POD, FAR i Peirce wobec „zawsze susza” i klimatologii gminy; „Raport PDF” otwiera widok do druku.
7. **Data dzisiejsza** (scena „Raport na dziś: poza okresem monitoringu suszy”): działka 2, 21.11.2026, „Rośliny strączkowe”. Raport mówi
   „poza okresem monitoringu suszy (21.III–30.IX)”, podaje wynik sezonu 2026 i plan przed następnym sezonem (np. zastawka na rowie po roztopach).

Tytuły scen w `demo/scenes.py`, dokładnie i w tej kolejności (są też w `DONE.json`):
```
Wskazanie działki na mapie | Działka z ewidencji na zdjęciu | Werdykt: bilans wobec progu z rozporządzenia | Cały raport w skrócie
Gdzie zatrzymać wodę na działce | Plan działań: przełącznik „W planie” | Zgodność z oceną państwa (SMSR) | Źródła, czasy i braki danych
Widok doradcy i raport PDF | Raport na dziś: poza okresem monitoringu suszy
```

## Raport: sekcje w tej kolejności

Kolejność jak w zadaniu: ocena → przyczyny → retencja → agrotechnika → nawadnianie. Każda sekcja: wykres (SVG z serwera), pod nim 2–3
zdania (co pokazuje, dlaczego ważne, gdzie patrzeć), potem „Jak to policzono”. Tekst to stałe szablony z podstawionymi wartościami,
zalecenia wybierają reguły na wskaźnikach, model językowy nie bierze udziału w wyniku.

0. **Werdykt i ocena bieżąca.** KBW = Σ opadu − Σ ET0 (FAO-56) w każdym z 14 okresów rozporządzenia (21.III–20.V … 1.VIII–30.IX)
   zakończonych do daty analizy. Plakietka „Bilans poniżej progu suszy (szacunek dla działki)”, gdy w którymkolwiek okresie KBW < próg dla
   grupy uprawy i kategorii gleby; na górze okres z najmniejszym zapasem (KBW − próg). Pod plakietką stałe zdanie: „To nie jest urzędowe
   stwierdzenie suszy; we wniosku liczy się ocena SMSR IUNG dla gminy”. Przed 20.V: bilans od 21.III do daty, „okres jeszcze trwa”, bez
   plakietki. Od 1.X do 20.III: „poza okresem monitoringu suszy” i wynik ostatniego sezonu. „Inna uprawa” i komórki „-”, „x” tabeli: sam
   bilans i zdanie, że rozporządzenie nie daje tu progu.
   - **Kategoria gleby** wybiera próg (zboża jare w okresie 1: kat. I −125 mm, kat. IV −194 mm). Odczyt warstwy IUNG
     `Susza:katgl_landuse2024` dla punktu, gdy działa; inaczej reguła z uziarnienia SoilGrids (sekcja „Modele i metody obliczeń”) ze
     zmierzoną zgodnością z mapą IUNG (`soil.category_agreement`). Gdy uziarnienie leży blisko granicy klas, raport podaje też wynik dla
     sąsiedniej kategorii. Doradca może kategorię poprawić.
   - **Wiersz SMSR:** symbol SMSR dla gminy, okresu, uprawy i kategorii gleby działki z tabeli dla roku daty analizy (jedna strona,
     ok. 0,14 s). Przed 2020 SMSR nie publikuje tabel gmin; raport to mówi.
   - **Wiersz satelity:** „Stan roślin na działce”: NDMI z ostatniej sceny bez chmur w obrysie wobec mediany tej samej dekady z N poprzednich
     sezonów (do 5, liczone w tle z limitem czasu; N w raporcie), czytany z fazą uprawy (spadek NDVI zbóż w lipcu to dojrzewanie, nie
     susza). Brak sceny bez chmur w 15 dniach przed datą albo brak historii: „brak” z powodem. Rolnik widzi słowa („rośliny suchsze niż
     zwykle w tej dekadzie”), doradca wartości NDVI i NDMI. Satelita nie zmienia bilansu ani plakietki.
   - **Działanie nr 1:** najwyżej postawione działanie retencyjne z sekcji 4, z numerem na zdjęciu i formalnością, albo „brak miejsca na
     działce, bo …”.
1. **Historia 10 sezonów.** Słupek = najgorszy zapas sezonu, kreska = próg, liczba sezonów pod progiem; dla lat od 2020 znacznik oceny SMSR gminy.
2. **Gmina i trafność metody.** Wynik SMSR gminy (symbol dla każdej kategorii gleby, udział powierzchni zagrożonej w %) obok wyniku działki,
   z przyczyną różnicy; zgodność według odległości od progu, tabela 2×2 i miary z sekcji „Pomiar zgodności z SMSR” z `metrics.json`.
3. **Przyczyny.** Wykres kaskadowy: zwykły bilans tego okresu (mediana 10 sezonów) → mniej opadu → więcej parowania = wynik. Gleba słowami
   IUNG („bardzo podatna na suszę”, kat. I), spadek terenu z NMT, przebieg NDVI i NDMI w sezonie wobec mediany poprzednich sezonów.
4. **Zatrzymanie wody.** Miejsce każdego działania liczy aplikacja z analizy spływu (sekcja „Modele i metody obliczeń”): siatka wysokości
   GUGiK z marginesem ok. 300 m wokół działki, bo woda spływa od sąsiadów i do nich. Wynik: linie spływu skoncentrowanego, punkty
   wypływu i dopływu na granicy działki z powierzchnią zlewni w ha, rowy, cieki i zbiorniki z BDOT10k, profil terenu. Kandydaci na
   miejsca idą malejąco po przechwyconej zlewni; raport pokazuje najwyżej 3, każde z tą liczbą. Progi rozmieszczania są z podręcznika
   ACPF v7.0 (USDA ARS, 06/2025), przeliczone na jednostki metryczne, każdy ze stroną podręcznika w kolumnie źródła katalogu:
   - rów zadarniony (pas trawy w linii spływu skoncentrowanego), gdzie indeks siły strumienia SPI = ln(SCA · tan β) przekracza próg
     z podręcznika, na odcinku co najmniej 50 m, z długością w m; pas trawy na odcinku granicy z wypływem;
   - pasy konturowe przy nachyleniu działki 4–15%; uprawa w poprzek stoku, prostopadle do średniego spadku;
   - drenaż kontrolowany (regulowany odpływ z drenów) na gruntach zdrenowanych przy nachyleniu ok. 1% lub mniej;
   - zastawka tylko, gdy linia spływu z działki dochodzi do rowu z BDOT10k; liczba zastawek ≈ długość odcinka rowu × spadek rowu
     (z modelu terenu wzdłuż rowu) / wysokość piętrzenia;
   - gdy wypływ trafia na pole sąsiada: pas przy tej granicy i niecka w najniższym punkcie wewnątrz działki;
   - pozostałe działania rozmieszczania ACPF z progami z podręcznika i stroną; próg bez sprawdzonej strony: „propozycja zespołu”.
   Gdy spadek działki jest za mały, by wiarygodnie wskazać linię spływu, raport pisze to wprost i nie rysuje strzałek. Gdy żadne miejsce
   nie spełnia warunku: „brak miejsca na działce, bo …”. Milimetrów ani m³ wody odpływającej z działki nie podajemy: współczynnik spływu
   nie ma źródła; efekt działania tylko jako zakres z literatury z dopiskiem „literatura”.
   Formalność z `app/advice/prawo_wodne.csv` (działanie, artykuł, cytat przepisu, strona PDF tekstu jednolitego Dz.U. 2026 poz. 1335,
   data sprawdzenia):
   - „nic nie trzeba”: zatrzymywanie wody w rowie i hamowanie odpływu z drenów istniejącym urządzeniem (art. 395 pkt 11, 12), gdy skutek
     zostaje na własnym gruncie albo za pisemną zgodą sąsiadów;
   - „powiadomienie Wód Polskich”: przebudowa rowu lub drenów w celu zatrzymania wody, w tym nowa zastawka na rowie (art. 395 pkt 15,
     16 i art. 395a);
   - „zgłoszenie”: staw do 5000 m² i 3 m głębokości, zasilany tylko opadem, roztopami lub wodą gruntową (art. 394 ust. 1 pkt 9);
   - „pozwolenie”: pobór ponad 5 m³/dobę średniorocznie (art. 34 pkt 12, art. 389 pkt 2);
   - „sprawdź w Wodach Polskich”, bez numeru artykułu: działanie, dla którego tekst ustawy nie rozstrzyga formalności.
   Przy każdym działaniu zmieniającym odpływ: art. 234 ust. 1 (bez szkody dla gruntów sąsiednich); rów poza działką: potrzebna pisemna
   zgoda sąsiada albo spółki wodnej. Przy zastawce ostrzeżenie: w mokrym okresie piętrzenie trzeba obniżyć, by nie zalać pola własnego
   ani sąsiada.
5. **Uprawa gleby.** Wykres: w ilu z 10 sezonów każda dekada IV–IX była pod progiem, pod nim kalendarz zabiegów do następnego okna suszy.
   Reguły: mulcz i resztki, międzyplon (na glebie bardzo lekkiej wymarzający), uprawa bez orki, w poprzek stoku, wcześniejszy siew lub forma
   ozima, porównanie grup upraw na tej glebie („zboża jare: pod progiem w 4 z 10 lat, zboża ozime: 1 z 10”, te same dane, inne progi).
6. **Plan i termin.** Oś czasu do następnego okna suszy (koniec ostatniego okresu z progiem dla grupy upraw) z działaniami z sekcji 4, 5
   i 7, przełącznik „W planie” przy każdym, licznik „N z M działań w planie”, stan w linku i w PDF. Nad osią zdanie prognozy przekroczenia
   progu do końca okresu krytycznego z jednym zdaniem trafności (sekcja „Prognoza przekroczenia progu”). Dla dat z przeszłości obok stoi,
   co się wydarzyło w okresach kończących się po dacie oceny (bilans z archiwum).
7. **Nawadnianie.** „Teraz tak / nie” z powodem (faza uprawy, woda w strefie korzeni wg FAO-56), dawka w mm i m³ na działkę (CDR 2025:
   20–25 mm na glebach lekkich, 30–35 mm na średnich), źródło wody z BDOT10k, pozwolenie powyżej 5 m³/dobę średniorocznie (art. 33 ust. 4
   pkt 1, art. 34 pkt 12).
8. **Źródła i ograniczenia.** Źródło, co dało, godzina, czas, stan (jest / zapas / szacunek / brak / kopia z dnia), rozdzielczość; czego
   raport nie uwzględnia (drenowanie, wody gruntowe, faktyczna data siewu); źródło kategorii gleby i jej wpływ na wynik, odległość stacji.

## Modele i metody obliczeń

Ocena bieżąca nie używa uczenia maszynowego: każdą liczbę daje rachunek albo reguła, więc nie ma wag do uczenia ani wycieku danych.
- **Ocena bieżąca:** rachunek bilansu, opad minus parowanie (ET0 FAO-56) w oknie 6 dekad, i porównanie z progiem z Dz.U. 2019 poz. 739
  dla grupy uprawy i kategorii gleby.
- **Kategoria gleby:** reguła przypisująca uziarnienie 0–30 cm (piasek, pył, ił z SoilGrids) do kategorii I–IV, z sąsiednią kategorią
  przy granicy klas. Mapa IUNG, gdy odpowiada dla punktu, jest odczytem, nie modelem; na niej mierzymy zgodność reguły.
- **Roślinność:** odchylenie NDVI i NDMI od mediany tej samej dekady w poprzednich sezonach na tej samej działce (własna historia
  działki, nie średnia regionu).
- **Spływ:** siatka wysokości GUGiK 10 m z wysokościami zaokrąglonymi do 0,1 m i marginesem ok. 300 m; wewnątrz działki siatka 5 m,
  gdy mieści się w limicie punktów i czasu. Jak w ACPF wypełniamy zagłębienia płytsze niż ok. 0,2 m, a głębsze zostają; potem obsługa
  płaskich fragmentów. Akumulację (powierzchnia zlewni w ha) liczymy dwiema metodami: D8 (jeden kierunek na oczko; tak ACPF liczy
  akumulację) i D-nieskończoność Tarbotona (woda dzielona między dwóch niższych sąsiadów proporcjonalnie do spadku; ACPF używa jej
  tylko do SPI i TWI). ACPF zakłada model terenu 1–2 m, nasza siatka jest rzadsza, więc metodę wybiera pomiar: punkt wypływu z D8,
  z D-nieskończoności i najniższy punkt granicy idą do testu rowów (sekcja „Sprawdzenie miejsc retencji”); aplikacja używa najlepszego,
  porównanie idzie do README. Linia spływu skoncentrowanego = akumulacja powyżej progu; SPI = ln(SCA · tan β) z D-nieskończoności,
  jak w ACPF (SCA: zlewnia na metr szerokości oczka, β: spadek oczka). Rachunek w numpy (działa w Windows), w jednym wymiennym module
  `app/advice/placement.py`.
- **Źródło metody rozmieszczania:** ACPF (Agricultural Conservation Planning Framework, USDA ARS). README cytuje Tomer i in. 2013
  (J. Soil Water Conserv. 68(5), 113A–120A), Tomer i in. 2015 (J. Environ. Qual. 44(3), 754–767) i podręcznik ACPF v7.0 (Porter
  i in. 2025); DOI podajemy dopiero po sprawdzeniu, że prowadzą do tych prac. Kodu ani tekstu ACPF nie kopiujemy (narzędzia pobiera
  się po przyjęciu umowy, której treści nie znamy): katalog podaje stronę podręcznika bez cytatu. ACPF daje tylko część
  rozmieszczania; ocena suszy, progi z rozporządzenia, formalności z Prawa wodnego i raport są nasze.
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
  Brier, BSS i kalibrację. Po końcu okresu krytycznego: „okres krytyczny dla tej uprawy już minął”; „Inna uprawa”: brak
  progu, więc brak prognozy.

## Skąd biorą się rekomendacje

Baza: 26 działań spisanych ze źródeł (11 retencji krajobrazowej, 11 glebowych i agrotechnicznych, 4 nawadniania; CDR 2025, katalog NWRM
Komisji Europejskiej, IUNG, FAO-56, ACPF, załącznik organizatora) w katalogu CSV (`app/advice/catalog*.csv`). Kolumny: działanie, grupa,
przyczyny, warunki (każdy próg w osobnej kolumnie), efekt (od, do, jednostka), źródło (dokument, strona, dosłowny cytat, adres), poziom
pewności (badanie / opinia ekspercka / propozycja zespołu), formalność (artykuł), termin. Liczba trafia do raportu tylko z wypełnionym
źródłem i cytatem; test to sprawdza. Efekt działania tylko jako zakres z literatury, oznaczony „literatura”. Wiersze z progami ACPF
(rów zadarniony, pasy konturowe, drenaż kontrolowany i inne) mają progi w jednostkach metrycznych i stronę podręcznika v7.0, bez cytatu.
1. Diagnoza przyczyn z danych działki: za mało opadu, gleba słabo trzyma wodę, woda spływa z pola, uprawa wrażliwa w tej fazie. Wszystkie
   spełnione reguły dają przyczyny; nad działaniami stoi lista rozpoznanych przyczyn z liczbami działki.
2. Dopasowanie: każde działanie jest przypisane do przyczyn, na które działa (mulcz i międzyplon ograniczają parowanie i poprawiają
   glebę; zastawka i pas przy rowie zatrzymują odpływ; nawadnianie uzupełnia brak opadu). Bez przyczyny nie ma zalecenia.
3. Warunki stosowania: działanie odpada, gdy nie pasuje do działki (głęboszowanie tylko na glebach średnich i ciężkich; regulowany
   odpływ tylko na gruntach zdrenowanych o spadku do 1%; zastawka tylko, gdy linia spływu dochodzi do rowu).
4. Kolejność w grupie: wyżej działanie odpowiadające na więcej przyczyn naraz; dalej wykonalność w terminie od daty oceny i to, czy
   rolnik zrobi je sam. Najwyżej 3 działania na grupę; grupy w kolejności zadania (retencja, agrotechnika, nawadnianie).
5. Stałe zdanie z podstawionymi liczbami tej działki (powierzchnia, spadek, zlewnia w ha, odległość do rowu, niedobór w mm, termin,
   miejsce).

Progi rozmieszczania mają stronę podręcznika ACPF. Progi bez potwierdzonego źródła (np. odległość od rowu, wysokość piętrzenia) mają
poziom pewności „propozycja zespołu”; widok doradcy tak je opisuje.

## Pomiar zgodności z SMSR

Liczba z walidacji: **CSI wyniku „pod progiem / nad progiem” względem symboli SMSR IUNG**, z POD, FAR i wskaźnikiem Peirce'a
(POD − POFD); tabela 2×2 jak w weryfikacji prognoz, CSI = a/(a+b+c) pomija zgodne „brak”.
- Przypadek: gmina × rok × okres × grupa uprawy × kategoria gleby z symbolem „+” lub „-” w tabelach SMSR („x”, „#”, „*”, „n” pomijamy).
- Niezależność: KBW jest jeden dla gminy, roku i okresu; symbole 14 grup i 4 kategorii to ten sam bilans z różnymi progami, a kolejne
  okresy dzielą 50 z 60 dni. Wielkość próby podajemy więc w gmino-latach testowych (`smsr.n_gmina_years`, cel co najmniej 300), liczbę
  symboli obok, a bootstrap losuje gminy.
- Zbiór: ok. 200 gmin losowanych warstwowo po 16 województwach, lata 2020–2026 (`scripts/fetch_smsr.py` → `data/raw/smsr/`, ok. 16 min).
  Podział z góry: 50 gmin do wyboru wzoru ET0, 150 do testu liczonego raz. Nasz wynik liczy ten sam kod co aplikacja (`fetch_weather`
  dla centroidu gminy, KBW, progi z rozporządzenia), z tą samą kolejnością źródeł pogody.
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
działkach na ortofotomapie, ze zrzutami ekranu.
- **Wypływ wobec rowu:** ok. 50 działek z rowem BDOT10k do 50 m od granicy; odsetek działek, w których punkt wypływu leży do 30 m od
  rowu, dla D8 (`retention.outlet_hit_d8`), D-nieskończoności (`retention.outlet_hit_dinf`), najniższego punktu granicy
  (`retention.outlet_hit_lowest`) i 100 losowych punktów granicy (`retention.outlet_hit_random`). Aplikacja używa metody z najwyższym
  wynikiem (przy remisie prostszej: najniższy punkt, potem D8); jej wynik to `retention.outlet_hit_share`. Rów jest zagłębieniem
  w modelu terenu, więc wynik jest optymistyczny; README to mówi i pokazuje porównanie czterech wariantów.
- **Zbiorniki:** zbiorniki i oczka z BDOT10k w promieniu ok. 1 km od działek; AUC akumulacji w miejscach zbiorników wobec losowych
  miejsc (`retention.pond_auc`).

## Odrębność

Typowe rozwiązanie tego zadania, jakiego się spodziewamy: mapa, NDVI, semafor „ryzyko wysokie” z własnego indeksu, porady z modelu językowego
albo z szablonu bez warunku, bez walidacji. Forma jest podobna (mapa + raport), różnica jest sprawdzalna: bilans definicją prawną suszy
w mm wobec progu, który zna każdy, kto składał wniosek suszowy, obok oceny SMSR dla gminy; zmierzona zgodność z oceną państwa na co
najmniej 300 gmino-latach, porównana z odpowiedziami trywialnymi; prognoza przekroczenia progu sprawdzona na odłożonych latach wobec
częstości historycznej; zalecenie z przyczyn i warunku, retencyjne z miejscem z analizy spływu z progami podręcznika ACPF ze stroną
(metoda wypływu wybrana pomiarem wobec rowów spośród D8, D-nieskończoności i najniższego punktu granicy, obok losowych punktów)
i formalnością z cytatem przepisu; ten sam numer i data dają zawsze ten sam raport; braki
danych wprost; działanie sprawdzone na 50 losowych działkach, także z datą listopadową.

## Dane

Źródła, licencje, rozmiary i daty: `docs/DANE.md`. Pobieranie dla działki jest napisane i zmierzone (10 źródeł, każde ze stanem, czasem i
adresem; 10 działek: 6,1 s typowo, 8,7 s najgorzej, 10 ms z pamięci podręcznej) i leży w `app/geodata` z testami. Działka z punktu na
mapie: ULDK GetParcelByXY; kafle mapy: mapa podkładowa i ortofotomapa GUGiK. Pogoda: Open-Meteo, a gdy odmawia, posterunki IMGW + ET0
FAO-56 ze stacji synoptycznej, luki z NASA POWER. Dochodzą: tabele gmin SMSR IUNG (wiersz gminy na żywo, archiwum do pomiaru), kategoria
gleby z warstwy IUNG, progi z Dz.U. 2019 poz. 739 w CSV z testem, katalog działań (CDR 2025, NWRM, ACPF), formalności Prawa wodnego
w CSV z cytatami, siatka wysokości GUGiK z marginesem ok. 300 m, rowy, zbiorniki i oczka z BDOT10k do testu miejsc, pogoda 2001–2026 dla centroidów 200 gmin (2020–2026 do pomiaru zgodności, 2001–2025 do walidacji prognozy), prognoza 16 dni
Open-Meteo, mapa upraw JRC EUCROPMAP 2022 czytana oknem w obrysie. Danych syntetycznych w produkcie nie ma; dane demo to prawdziwe
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
9. Kodu ani tekstu ACPF (cytujemy metodę i stronę podręcznika) ani bibliotek hydrologicznych bez działającej wersji dla Windows;
   spływ liczymy w numpy.
10. Niczego innego z listy „Otwarte decyzje”, dopóki nie zapadnie decyzja.

## Moduły krytyczne dla jury

Małe, typowane, z testami i opisem w `docs/PYTANIA_JURY.md`:
1. `app/drought/kbw.py` + `app/drought/progi_dz_u_2019_739.csv`: 14 okresów, KBW, próg, wynik, stany „poza okresem” i „brak progu”;
   test porównuje CSV (14 grup × 4 kategorie × 14 okresów) z rozporządzeniem.
2. `app/advice/rules.py` + `app/advice/catalog*.csv` + `app/advice/prawo_wodne.csv`: reguła = przyczyny i warunek na wskaźnikach →
   szablon zdania, liczby, termin, źródło, formalność; kolejność po liczbie przyczyn, wykonalności i tym, czy rolnik zrobi to sam. Testy:
   każde działanie ma w CSV artykuł, cytat, stronę PDF i datę sprawdzenia albo „sprawdź w Wodach Polskich” bez numeru artykułu; liczba
   efektu tylko z cytatem źródła; progi ACPF w jednostkach metrycznych ze stroną podręcznika. Progi bez źródła w widoku doradcy
   opisane jako propozycje zespołu.
3. `app/advice/placement.py`: analiza spływu (wypełnienie zagłębień płytszych niż 0,2 m, akumulacja D8 i D-nieskończonością w ha, SPI)
   i miejsca działań z progami ACPF albo „brak miejsca, bo …”. Typowane wejście (obrys, siatka wysokości z marginesem, wody z BDOT10k) i wyjście (lista miejsc z rodzajem,
   położeniem, zlewnią w ha i powodem); moduł da się wymienić bez zmian w reszcie raportu.
4. `app/validation/agreement.py`: tabela 2×2, trafność, trafność zrównoważona, czułość, precyzja, CSI, POD, FAR, Peirce, linie
   odniesienia, bootstrap po gminach; wołany przez `scripts/eval_smsr.py`.
5. `app/forecast/exceedance.py`: częstość historyczna, dopełnianie przebiegami i model za jednym typowanym interfejsem, stany „ok”,
   „okres minął”, „brak progu”; podział po latach i miary (Brier, BSS, kalibracja) w `scripts/eval_forecast.py`; test, że rok Y nie
   widzi lat ≥ Y.

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
| IUNG liczy ewapotranspirację innym wzorem niż FAO-56 | wzór wybieramy na 50 gminach rozwojowych; różnicę opisujemy w ograniczeniach |
| Opad ze stacji i z siatki różni się w oknie 60 dni typowo o 29 mm | pytanie do mentora; kolejność źródeł bez zmian do odpowiedzi; CSI na samej siatce jako linia odniesienia |
| Błędny numer artykułu Prawa wodnego | CSV z cytatem, stroną i datą sprawdzenia; test; bez potwierdzonego przepisu „sprawdź w Wodach Polskich” |
| Open-Meteo archiwum odrzuca limitem dziennym | łańcuch IMGW + NASA POWER, pamięć podręczna, dostawca i odległość stacji w raporcie |
| SMSR ogranicza pobieranie archiwum | przerwy 0,5 s, mniejsza próba z podanym N; 84 strony już sparsowane |
| Satelita lub NMT przekracza limit czasu | nie blokują bilansu; wiersz mówi „brak” i dlaczego; historia satelity dociąga się w tle |
| Ani D8, ani D-nieskończoność nie bije najniższego punktu granicy w teście rowów | aplikacja używa najniższego punktu granicy; porównanie czterech wariantów w README |
| Siatka z marginesem 300 m przekracza limit punktów lub czasu | w działce 10 m zamiast 5 m, poza działką co 20–30 m; zlewnia przycięta do marginesu, raport to mówi |
| Wysokości zaokrąglone do 0,1 m dają płaskie fragmenty | wypełnienie zagłębień płytszych niż 0,2 m i obsługa płaskich fragmentów; za mały spadek: zdanie zamiast strzałek |
| Próg SPI z podręcznika ACPF (model 1–2 m) na siatce 10 m wskazuje za mało albo za dużo rowów zadarnionych | próg z podręcznika zostaje; liczba rowów zadarnionych na 50 działkach testowych w README; inny próg tylko jako „propozycja zespołu” z powodem |
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
- **Źródło opadu:** stacja czy siatka (różnica w oknie 60 dni typowo 29 mm, najwięcej 139 mm, może zmienić werdykt); pytanie do mentora.
- **Progi reguł poza rozmieszczaniem ACPF** (odległość od rowu, wysokość piętrzenia, warunki agrotechniki): od mentorów; do tego czasu
  propozycje zespołu. Reguły z tymi progami budujemy.
- Czym jest referencja jury i w jakim formacie poda numer działki (pytania do mentorów); nazwa produktu.

## Drabina cięć

- **L0:** opis, zrzuty, tabela progów i metoda w README.
- **Szkielet (sob 16:30):** `app/geodata` z testami; `app/drought/kbw.py` z CSV progów; wynik i widok do druku dla dowolnej działki
  i daty. W tle od razu: `scripts/fetch_smsr.py` (ok. 16 min) i pogoda 2001–2026 dla 200 gmin. Pierwsze 20 min: odczyt warstwy IUNG
  `Susza:katgl_landuse2024` dla 10 działek z pomiaru czasu.
- **L1 (sob 20:00):** dowolna działka i data, także listopadowa: wejście numerem albo klikiem na mapie startowej (przybliżanie, ULDK
  GetParcelByXY, obrys i numer do potwierdzenia „To ta działka” / „Wskaż inną”), klik w sąsiednią działkę na zdjęciu raportu z propozycją
  przejścia, zdjęcie z obrysem, werdykt z wykresem bilansu, plakietką i zastrzeżeniem, wiersz SMSR gminy dla daty analizy, wiersz stanu
  roślin z satelity, działanie retencyjne nr 1 (najniższy punkt obrysu z siatki wysokości + najbliższy rów z BDOT10k + formalność z CSV),
  agrotechnika i nawadnianie jako zdania z reguł, skrót, źródła i braki, widok do druku.
- **L2 (ndz 02:00):** `smsr.*` w `metrics.json` z miarami dla rolnika i sekcja gminy, 10 sezonów i lista przyczyn, analiza spływu
  (margines 300 m, zagłębienia płytsze niż 0,2 m wypełnione, D8 i D-nieskończoność, SPI, zlewnia w ha, linie spływu, wypływy
  i dopływy) z miejscami działań i progami ACPF ze stroną, cytaty metody w README, katalog działań CSV ze źródłami i kolejnością po
  liczbie przyczyn, wykresy agrotechniki i nawadniania, plan z przełącznikami i osią czasu, `soil.category_agreement`, test 50 działek
  z `retention.*` (test wypływu wobec rowów dla D8, D-nieskończoności, najniższego i losowych punktów) i `robustness.*`, przełącznik
  Rolnik / Doradca, prognoza dopełnianiem przebiegami nad osią planu z `forecast.*` z walidacji kroczącej.
- **L3 (ndz 09:00, potem bez nowych funkcji):** model prognozy w aplikacji, jeśli wygrał; podpowiedź uprawy z mapy JRC; siatka 5 m
  wewnątrz działki; pełny widok doradcy; bilans FAO-56 w nawadnianiu; układ na telefon; wyszukiwanie po nazwie obrębu; dopracowanie
  wyglądu.
- **Kolejność cięcia:** podpowiedź uprawy → siatka 5 m w działce (zostaje 10 m) → test zbiorników (`retention.pond_auc`) → model prognozy w aplikacji (zostaje dopełnianie,
  porównanie w README) → analiza spływu w aplikacji (zostaje najniższy punkt granicy z L1, test rowów w README) → bilans FAO-56
  w nawadnianiu (zostaje prosta decyzja) → wykres gminy w sekcji 2 (wiersz SMSR zostaje) → stan planu w linku i PDF (przełącznik
  w raporcie należy do złotej ścieżki i zostaje).
- **Nigdy nie tniemy:** złotej ścieżki, wskazania działki na mapie (obowiązkowy zakres zadania, pkt 3.3 ppkt 2), liczby zgodności z SMSR,
  wiersza SMSR gminy i zdania zastrzeżenia pod werdyktem, działania retencyjnego nr 1 z miejscem, daty poza okresem monitoringu, jawnych
  braków danych, działania dla dowolnej działki.

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
