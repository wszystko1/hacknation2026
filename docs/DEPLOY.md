# Wdrożenie na serwer (VPS) i uruchomienie na Windows

Repozytorium jest prywatne do końca konkursu, więc kod trafia na serwer przez `rsync` z laptopa, nie przez `git clone`.
W repozytorium nie ma sekretów; skrypty nie zapisują kluczy.

## a) Szybka ścieżka

1. W panelu Hetzner Cloud (Console, Add Server): obraz Ubuntu 24.04, typ x86 z 2 vCPU / 4 GB (np. CPX21 lub CX32), lokalizacja Falkenstein/Nuremberg/Helsinki,
   uwierzytelnianie kluczem SSH (klucz publiczny laptopa dodany przy tworzeniu; bez klucza Hetzner wysyła hasło roota mailem i skrypty nie zadziałają). Zapisz adres IPv4.
2. Na laptopie, w katalogu repozytorium: `./deploy/deploy.sh <IP>` (opcjonalnie `--warm`, opcjonalnie domena jako drugi argument).
   Pierwszy raz trwa 10–20 minut (aktualizacje systemu, uv, Python 3.12, Caddy, zależności).
3. `./deploy/smoke.sh https://<IP z myślnikami>.sslip.io` (np. `https://203-0-113-7.sslip.io`). Oczekiwane: `SMOKE PASS`.

Logowanie przez inne konto z sudo zamiast roota: `SSH_USER=ubuntu ./deploy/deploy.sh <IP>`.

## b) Co robi każdy skrypt

- `deploy/bootstrap.sh`: uruchamiany na serwerze jako root (przez `deploy.sh`), idempotentny. Aktualizuje system i włącza
  automatyczne poprawki bezpieczeństwa, dodaje 2 GB swapu, zapora ufw (22/80/443), użytkownik `deploy` (bez hasła, sudo bez hasła,
  klucze skopiowane od roota), uv w przypiętej wersji i Python 3.12 (`/opt/uv-python`), Caddy z oficjalnego repozytorium,
  katalogi `/srv/bilans/app` i `/var/lib/bilans/geodata_cache`, plik `/etc/bilans.env` (`GEODATA_CACHE_DIR`), usługa systemd `bilans`
  (uvicorn, 2 procesy, 127.0.0.1:8000) i Caddyfile (HTTPS, kompresja, nagłówki bezpieczeństwa, `Cache-Control` 5 min dla `/static`).
  Host: `<IP z myślnikami>.sslip.io` albo domena z drugiego argumentu.
- `deploy/deploy.sh <IP> [domena] [--warm] [--bootstrap]`: sprawdza SSH, uruchamia bootstrap tylko gdy serwer jeszcze go nie miał
  (albo z `--bootstrap`), `rsync` kodu (bez `.git`, `.venv`, `data/raw`, `artifacts`, `docs/img`, wideo, logów; zostają `demo/data`
  i kafle map; ok. 15 MB), `uv sync --frozen --no-dev`, restart usługi, wypisuje adres https.
- `deploy/smoke.sh <URL>`: `/health`, ekran startowy, raporty dla dwóch działek demo, zimny raport dla `160204_5.0001.101`,
  odpowiedź ULDK (wielokąt, nie atrapa) z maszyny, na której skrypt biegnie; wynik PASS/FAIL z czasami.
- `deploy/warm.sh [URL] [N]`: sekwencyjnie podgrzewa cache dla działek demo i kilku z `demo/data/eval/parcels50.csv` (limit 20 min).
- `deploy/windows/start.bat`, `start.ps1`: start na Windows bez `make` (patrz `deploy/windows/README.md`).

## c) Aktualizacja po zmianie kodu

`./deploy/deploy.sh <IP>`: tylko rsync, `uv sync`, restart (kilkadziesiąt sekund).

## d) Logi i restart

Na serwerze (`ssh deploy@<IP>`): `journalctl -u bilans -f`, `sudo systemctl restart bilans`, `systemctl status bilans`,
logi Caddy: `journalctl -u caddy -f`. Użycie pamięci: `free -h`.

## e) Rozwiązywanie problemów

- **ULDK zwraca atrapę / smoke FAIL na ULDK:** niektóre sieci podstawiają `integracja01.gugik.gov.pl`. Test z serwera:
  `curl "https://uldk.gugik.gov.pl/?request=GetParcelById&id=040303_2.0002.189/13&result=geom_wkt&srid=2180"` ma dać `POLYGON((`.
  Aplikacja odrzuca atrapę (`app/geodata/uldk_guard.py`). Gdy ULDK nie działa z serwera, zmień region/dostawcę.
  Uwaga: smoke.sh odpytuje ULDK z maszyny, na której go uruchomisz; uruchom go też na serwerze: `bash /srv/bilans/app/deploy/smoke.sh http://127.0.0.1:8000`.
- **Brak pamięci (OOM):** `dmesg | grep -i kill`; zmniejsz `--workers` na 1 w `/etc/systemd/system/bilans.service`, potem
  `sudo systemctl daemon-reload && sudo systemctl restart bilans`.
- **Certyfikat Let's Encrypt:** Caddy pobiera go sam przy pierwszym wejściu na HTTPS; potrzebuje otwartych portów 80 i 443
  (ufw je otwiera; sprawdź też Cloud Firewall w panelu Hetznera, jeśli go dołączono do serwera). Błędy: `journalctl -u caddy`. `sslip.io` jest wspólną domeną publiczną,
  więc limit Let's Encrypt (50 certyfikatów na domenę tygodniowo) bywa wyczerpany; wtedy użyj własnej domeny
  (rekord A na IP): `./deploy/deploy.sh <IP> moja.domena.pl`. Wielokrotne `--bootstrap` nie zużywa limitu (Caddy trzyma certyfikat).
- **`ssh` odmawia dostępu:** klucz musi być na koncie root (lub ustaw `SSH_USER`).

## f) Koszty i usunięcie serwera po konkursie

Serwer Hetzner x86 z 2 vCPU / 4 GB kosztuje kilka euro miesięcznie, rozliczany godzinowo. **Po konkursie usuń serwer** w Hetzner Console
(Server, Delete). Samo wyłączenie nie zatrzymuje opłat za serwer i adres IP. Sprawdź, że nie zostały snapshoty, wolumeny ani dodatkowe IP.

## g) Co NIE jest sprawdzone

Skrypty nie były uruchomione na prawdziwym serwerze: `bootstrap.sh` (apt, Caddy, systemd, ufw), certyfikat HTTPS i `deploy.sh`
przez SSH przeszły tylko `bash -n` i shellcheck. Lokalnie sprawdzono aplikację z komendą z jednostki systemd (2 procesy,
`GEODATA_CACHE_DIR`) i `smoke.sh`. Skryptów Windows nie testowano. Próba bez Dockera i bez serwera (świeże `uv sync`, zużycie pamięci, przegląd skryptów) jest opisana w `docs/notes/wdrozenie-proba.md`.
