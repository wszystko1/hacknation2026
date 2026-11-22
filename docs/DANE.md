# Dane

Stan na 21.11.2026. W działającej aplikacji każde źródło działki jest pobierane na żywo przy zapytaniu, a raport podaje adres, godzinę
i czas pobrania. Wcześniej pobrane są: archiwum IMGW (indeks stacji), archiwum tabel SMSR do pomiaru zgodności, pogoda wieloletnia dla
gmin z próby do oceny prognozy, próbki demo w `demo/data/` i odpowiedzi testowe w `tests/fixtures/`. Danych syntetycznych w produkcie
nie ma; testy indeksów satelitarnych tworzą małe rastry syntetyczne w samym teście.

## Źródła pobierane dla działki

| Źródło | Co bierzemy | Adres | Licencja | Rozdzielczość | Ograniczenia |
|---|---|---|---|---|---|
| ULDK GUGiK | obrys działki, województwo, powiat, gmina, obręb, numer | https://uldk.gugik.gov.pl/ | dane publiczne GUGiK, bezpłatne (Prawo geodezyjne i kartograficzne, art. 40a) | wektor EGiB, EPSG:2180 | stan bieżący ewidencji, bez historii podziałów |
| Ortofotomapa GUGiK (WMS) | zdjęcie otoczenia działki | https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution | jak wyżej | piksel źródłowy 0,25 m lub lepszy | zdjęcie z ostatniego nalotu, nie z dnia analizy |
| Open-Meteo Historical Weather API | dobowy opad i ET0 FAO-56 | https://archive-api.open-meteo.com/v1/archive | CC BY 4.0, darmowo tylko niekomercyjnie | ERA5-Land ok. 9 km | dzienny limit zapytań (21.11.2026: HTTP 429) |
| IMGW-PIB, dane dobowe | opad z posterunków, dane synoptyczne do ET0 FAO-56 | https://danepubliczne.imgw.pl/data/dane_pomiarowo_obserwacyjne/dane_meteorologiczne/dobowe/ | dane publiczne IMGW-PIB, z obowiązkiem podania źródła | pomiar punktowy; posterunek zwykle 0–25 km, stacja synoptyczna 0–45 km | archiwum kończy się 1–2 miesiące wstecz; w czerwcu 2025: 505 posterunków opadowych, 57 stacji synoptycznych |
| Współrzędne stacji IMGW | kod, nazwa, położenie (`app/geodata/data/imgw_stations.csv`) | https://github.com/bczernecki/climate | pakiet R `climate`, MIT | 2002 stacje | 436 z 505 posterunków opadowych ma współrzędne |
| NASA POWER | zapas pogody (opad, temperatura, wilgotność, wiatr, promieniowanie) | https://power.larc.nasa.gov/api/temporal/daily/point | dane NASA, otwarte | ok. 50 km | ostatnie 2–3 dni puste |
| Open-Meteo Forecast i Seasonal | 16 dni prognozy (cecha i dopełnienie w prognozie przekroczenia progu); prognoza sezonowa 183 dni, 51 przebiegów (nie w widoku rolnika) | https://api.open-meteo.com/v1/forecast , https://seasonal-api.open-meteo.com/v1/seasonal | CC BY 4.0, niekomercyjnie | kilka km; ok. 36 km | prognoza, nie pomiar |
| IUNG-PIB GeoServer, kategoria gleby | kategoria gleby I–IV w punkcie działki (źródło podstawowe, jeśli odczyt dla punktu działa) | https://sgeo.iung.pl/geoserver/ows , warstwa `Susza:katgl_landuse2024` (WMS; WCS `Susza__katgl_landuse2024`) | dane IUNG-PIB; warunków licencji nie ustaliliśmy | nie znamy | odczytu dla punktu (GetFeatureInfo, GetCoverage) jeszcze nie testowaliśmy |
| ISRIC SoilGrids 2.0 | piasek, pył, ił w warstwie 0–30 cm → kategoria gleby I–IV regułą (źródło zapasowe) | https://rest.isric.org/soilgrids/v2.0/properties/query | CC BY 4.0 | 250 m | 2–7 s na punkt; brak wartości dla części punktów; model globalny, nie polska mapa glebowo-rolnicza; zgodność z mapą IUNG mierzymy (`soil.category_agreement`) |
| Sentinel-2 L2A (Planetary Computer; sceny do mediany NDMI wilgotnych stref) | NDVI, NDMI z maską chmur SCL w obrysie: ostatnia scena bez chmur w 15 dniach przed datą i ta sama dekada w do 5 poprzednich sezonach (w tle, z limitem czasu) | https://planetarycomputer.microsoft.com/api/stac/v1/search | dane Copernicus, otwarte | 10 m i 20 m | od 2.11.2016; chmury; jedna scena: 3,9 s typowo, 6,6 s najgorzej na 10 działkach |
| ULDK GUGiK, `GetParcelByXY` | obrys i numer działki w klikniętym punkcie mapy startowej, do potwierdzenia przez użytkownika | https://uldk.gugik.gov.pl/ | dane publiczne GUGiK, bezpłatne | wektor EGiB, EPSG:2180 | 21–22.11.2026 usługa odpowiadała błędnie (przekierowanie na stronę zastępczą); kopia demo ma obrysy dwóch działek |
| EGiB WFS GUGiK (usługa zbiorcza), warstwa `ms:dzialki` | zapas obrysu i numeru działki, gdy ULDK nie odpowiada | https://mapy.geoportal.gov.pl/wss/service/PZGIK/EGIB/WFS/UslugaZbiorcza | dane publiczne GUGiK, dostęp bez klucza | wektor EGiB, EPSG:2180 (w osiach N, E) | sprawdzony na atrapach HTTP, nie z sieci sali; stan z 22.11.2026 |
| KIEG GUGiK (Krajowa Integracja Ewidencji Gruntów), GetFeatureInfo | identyfikator i nazwy działki w klikniętym punkcie (bez geometrii), gdy ULDK i EGiB WFS zawiodą | adres usługi: nie sprawdziliśmy; w kodzie jeszcze go nie ma | dane publiczne GUGiK, dostęp bez klucza (według opisu usługi, licencji nie sprawdzaliśmy osobno) | punkt, bez obrysu | obrys tylko z kopii lokalnej; stan z 22.11.2026 |
| Mapa podkładowa i ortofotomapa GUGiK (WMS/WMTS) | kafle mapy startowej i raportu, podawane przez nasz serwer | https://mapy.geoportal.gov.pl/ | dane publiczne GUGiK, bezpłatne | piksel źródłowy 0,25 m lub lepszy | w demo kafle zamrożone 21.11.2026 w `demo/data/map/tiles/` (podkład i ortofotomapa); poza obszarem kopii brak kafli bez sieci |
| Usługa wysokości GUGiK | siatka wysokości w obrysie i z marginesem ok. 300 m: spadek, najniższy punkt granicy, zlewnia i spływ D8 | https://services.gugik.gov.pl/nmt/ | dane publiczne GUGiK | NMT 1 m próbkowany co 10 m, wysokości co 0,1 m | duże działki: rzadsza siatka, do 4000 punktów |
| BDOT10k (WMS GUGiK) | rowy, cieki, kanały, zbiorniki i oczka wodne (także do testu miejsc retencji) | https://mapy.geoportal.gov.pl/wss/service/pub/guest/kompozycja_BDOT10k_WMS/MapServer/WMSServer | dane publiczne GUGiK | 1:10 000, odczyt z obrazu w pikselach 2 m | obrysy z obrazu mapy, nie z wektorów; nie wszystkie rowy polowe są w bazie |
| JRC EUCROPMAP 2022 | podpowiedź uprawy w obrysie | https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EUCROPMAP/2022/EU_CropMap_22_v1_stratum_EU27-HR.tif | CC BY 4.0, © Unia Europejska | 10 m, jeden sezon | plik 6,8 GiB czytany oknem; bez podziału zbóż na ozime i jare |
| SMSR IUNG, tabele gmin | wiersz oceny SMSR dla gminy działki i roku daty analizy; archiwum do pomiaru zgodności: symbole suszy dla 14 grup upraw × 14 okresów × 4 kategorie gleby, udział powierzchni zagrożonej w % | https://susza.iung.pulawy.pl/wykazy/{rok},{TERYT7}/ | dane publiczne IUNG-PIB, z podaniem źródła | gmina | lata 2020–2026; bez wartości KBW w mm; strona HTML ok. 40 KB, 0,14 s |

## Źródła do oceny metody (`make eval`, nie w aplikacji)

| Źródło | Co bierzemy | Adres | Licencja | Ograniczenia |
|---|---|---|---|---|
| Pogoda 2001–2026 dla 200 gmin: IMGW-PIB, dane dobowe, z luką z NASA POWER | opad i dane synoptyczne do ET0 dla centroidów 200 gmin z próby; 2020–2026 do pomiaru zgodności z SMSR, 2001–2025 do walidacji prognozy przekroczenia progu | jak wyżej | jak wyżej | pliki w `data/raw/` (poza repozytorium), pobiera je `scripts/fetch_commune_weather.py`; luki wypełnia siatka NASA POWER (ok. 50 km) |
| Open-Meteo Forecast, prognoza 16 dni | pierwsze 16 dni dopełnienia w prognozie przekroczenia progu (w aplikacji) | https://api.open-meteo.com/v1/forecast | CC BY 4.0, niekomercyjnie | prognoza, nie pomiar |
| JRC EUCROPMAP 2022 | podpowiedź uprawy i sprawdzian grup płodozmianu na próbie 50 działek | https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/EUCROPMAP/2022/EU_CropMap_22_v1_stratum_EU27-HR.tif | CC BY 4.0, © Unia Europejska | okno z pliku zdalnego; ULDK przekierowywał na stronę zastępczą, więc obrys próby to kwadrat 1 ha wokół punktu, nie działka z ewidencji |
| NASA POWER, dobowe od 1981 | luki w danych IMGW dla tych samych punktów | jak wyżej | jak wyżej | ok. 50 km |
| Open-Meteo Historical Forecast API | archiwalne prognozy 16 dni jako cecha w latach testowych | https://historical-forecast-api.open-meteo.com/v1/forecast | CC BY 4.0, niekomercyjnie | zakresu lat nie sprawdziliśmy; gdzie archiwum nie sięga, główny wynik liczymy bez tej cechy |
| IUNG-PIB, warstwa kategorii gleby | kategoria w ok. 100 punktach do pomiaru zgodności SoilGrids → kategoria | jak wyżej | jak wyżej | jeśli odczyt dla punktu nie działa, kategoria z koloru legendy na obrazie WMS |

## Tabele i przepisy przepisane do kodu

| Dokument | Co z niego bierzemy | Adres |
|---|---|---|
| Rozporządzenie MRiRW z 11.04.2019, Dz.U. 2019 poz. 739 (obowiązuje) | progi KBW: 14 grup upraw × 4 kategorie gleby × 14 okresów; kategorie gleby I–IV i ich WOD; zgodność z tabelą IUNG sprawdzona na jednym wierszu z każdej grupy (14 × 14 wartości) | https://eli.gov.pl/eli/DU/2019/739/ogl/pol/pdf |
| Prawo wodne, tekst jednolity Dz.U. 2026 poz. 1335 (225 stron) | formalności w `app/advice/prawo_wodne.csv` (artykuł, cytat, strona PDF, data sprawdzenia). Sprawdzone z tekstem 21.11.2026: art. 33 ust. 1–4, art. 34 pkt 1, 2, 12, art. 234 ust. 1, art. 389 pkt 1, 2, 6, art. 394 ust. 1 pkt 9, 10, art. 395 pkt 5, 7, 11, 12, 15, 16, art. 395a ust. 1–3. Numery stron dopisujemy przy budowie CSV | https://api.sejm.gov.pl/eli/acts/DU/2026/1335/text.pdf |
| FAO-56 (Allen i in. 1998), tab. 12 i 22 | Kc, głębokość korzeni, frakcja p do bilansu wody w strefie korzeni | https://www.fao.org/4/X0490E/x0490e0b.htm |
| CDR Brwinów 2025, „Melioracje, retencja i gospodarka wodna w rolnictwie” | dawki nawodnienia, mulcz, 5 m³/dobę = 0,5 mm na 1 ha | https://woda.cdr.gov.pl/images/publikacje/Publikacje/Melioracje_retencja_wodna_e-poradnik_2025.pdf |
| Katalog NWRM (Komisja Europejska) | nazwy i kody działań A01–A14, N01, N02; zasady słowne, gdzie stawiać działanie (miejsce na działce liczy nasz kod) | https://www.nwrm.eu/measures-catalogue |

## Rozmiary i daty pobrania

| Zbiór | Rozmiar | Pobrano | Gdzie |
|---|---|---|---|
| Archiwum IMGW 2015–2026 (opad, klimat, synop) | ok. 22 MB, 932 pliki | przy pierwszym uruchomieniu `python -m app.geodata imgw-sync` | `data/raw/imgw/` (poza repozytorium) |
| Archiwum IMGW 2001–2014 do prognozy | rozmiar zmierzymy przy pobraniu | `scripts/fetch_weather_history.py`, data w pliku wyniku | `data/raw/imgw/` (poza repozytorium) |
| Tabele SMSR do pomiaru: ok. 200 gmin × 7 lat | ok. 1400 stron, ok. 56 MB HTML | `scripts/fetch_smsr.py`, data w pliku wyniku | `data/raw/smsr/` (poza repozytorium) |
| Próbka SMSR sparsowana | 84 strony, 12 gmin z 12 województw | 21.11.2026 | jedna strona w `tests/fixtures/smsr/`; symbole zbóż ozimych i jarych (9408 wierszy, 12 gmin × 2020–2026) w `demo/data/eval/smsr_sample.csv` |
| Próbki demo: 040303_2.0002.189/13 (gm. Dobrcz, kopia na 15.07.2025, pogoda od 2015) i 100403_2.0011.144 (gm. Góra Świętej Małgorzaty, kopie na 20.06.2024 i 21.11.2026) | ok. 0,5 MB z obrazami | 21.11.2026 | `demo/data/geodata/` |

## Czego nie wiemy o danych

- Czy jury porównuje wynik z SMSR: nie potwierdzone przez organizatora.
- Jakim wzorem IUNG liczy ewapotranspirację w SMSR: nie sprawdziliśmy; my liczymy ET0 FAO-56.
- Warstwa kategorii gleby IUNG `Susza:katgl_landuse2024`: widoczna w opisie usługi, odczytu dla punktu nie testowaliśmy; licencji
  i rozdzielczości nie znamy.
- Od którego roku Open-Meteo trzyma archiwalne prognozy: nie sprawdziliśmy.
- Czy nowelizacje Prawa wodnego Dz.U. 2026 poz. 1358 i poz. 1156 zmieniają art. 33, 34, 389, 394, 395: nie otwieraliśmy ich.
- Czy nowa zastawka w istniejącym rowie to przebudowa rowu w celu zatrzymania wody (art. 395 pkt 15, powiadomienie) czy wykonanie
  urządzenia wodnego (art. 389 pkt 6, pozwolenie): tekst ustawy tego nie rozstrzyga; raport pisze „sprawdź w Wodach Polskich”.
- Współczynnika spływu dla pól uprawnych ze źródłem nie mamy, dlatego raport nie podaje objętości ani milimetrów odpływu.
