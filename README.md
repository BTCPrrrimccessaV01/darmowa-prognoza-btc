# Darmowa Prognoza BTC — uruchomienie krok po kroku

Całość działa za darmo na GitHub. Bot pracuje w chmurze, nie potrzebujesz otwartej przeglądarki ani własnego serwera.

## 1. Repozytorium
1. Załóż konto na github.com i utwórz **publiczne** repozytorium (np. `darmowa-prognoza-btc`).
   Publiczne = nielimitowane darmowe minuty Actions. Prywatne ma limit 2000 min/mies. na koncie darmowym.
2. Wgraj wszystkie pliki z zachowaniem struktury: `bot.py`, `index.html`, `README.md`, folder `.github/workflows/bot.yml`.
   (Najłatwiej: Add file → Upload files, a folder `.github` przeciągnij jako całość.)

## 2. Uprawnienia zapisu (ważne)
Settings → Actions → General → Workflow permissions → zaznacz **Read and write permissions** → Save.
Bez tego bot nie zapisze danych.

## 3. Pierwsze uruchomienie
Zakładka Actions → `darmowa-prognoza-btc` → Run workflow. Pierwszy bieg pobiera historię od 2015 (ok. 1–2 min).

## 4. Strona wyników
Settings → Pages → Source: Deploy from a branch → Branch: `main`, folder `/ (root)` → Save.
Strona pojawi się pod adresem `https://TWOJA-NAZWA.github.io/darmowa-prognoza-btc/`.
Otwórz ją na Windows (przeglądarka) i na Androidzie (Chrome → menu → „Dodaj do ekranu głównego”).

## 5. Alerty w tle na telefon (opcjonalnie, Telegram)
1. W Telegramie napisz do @BotFather → `/newbot` → skopiuj token.
2. Napisz cokolwiek do swojego bota, potem wejdź w `https://api.telegram.org/bot<TOKEN>/getUpdates` i znajdź `chat id`.
3. Settings → Secrets and variables → Actions → dodaj `TG_TOKEN` i `TG_CHAT`.

## Co robi bot (co 15 min, w UTC)
- Pobiera świece 6h z Coinbase (publiczne API, bez klucza) i składa je w świece 12h. Dopisuje tylko nowe zamknięte świece.
- Sprawdza 4 modele (bez fazy, faza cyklu, momentum, faza+momentum) × 8 poziomów wygładzania na całej historii (walk-forward). Wybiera najlepszy wg Brier score.
- Zapisuje każdą prognozę i po zamknięciu świecy rozlicza ją. Po 50 rozliczeniach, jeśli model przegrywa z rzutem monetą na żywo, przechodzi na 50%.
- Onchain i 10 portfeli z mempool.space. Log portfeli zapisuje tylko zmiany liczby transakcji.
- Wysyła alerty (duża zmienność, silna przewaga, cena przy strefie 1d) i zapisuje wynik do `state.json`.

## Zasady danych
- Pliki w `data/` są tylko dopisywane. Każdy bieg to commit w Git, więc poprzednie wersje zostają w historii.
- Ostrzeżenie: GitHub wyłącza harmonogram w publicznym repozytorium bez aktywności przez 60 dni. Bot commituje przy każdym biegu, więc zwykle to nie wystąpi. Sprawdzaj zakładkę Actions.
- Aby mieć własną kopię, co jakiś czas pobierz repozytorium jako ZIP (Code → Download ZIP).
- Harmonogram GitHub bywa opóźniony o kilka do kilkudziesięciu minut przy dużym obciążeniu. Strona pokazuje wiek danych.

## Spekulacja 0.33% (osobna zakładka)
- Moduł `spec033.py` działa niezależnie: własne dane w `data/spec033/`, własny stan w `spec_state.json`. Nie wpływa na prognozę główną.
- Zdarzenie: który poziom zostanie dotknięty pierwszy w ciągu 12 godzin, +0,33% czy −0,33% (świece 1h, dane Coinbase od 2016).
- Okna 12h nakładają się, więc niezależnych obserwacji jest około 12 razy mniej niż zdarzeń. Strona pokazuje to w przedziale ufności.
- Pierwsze uruchomienie pobiera historię godzinową (kilka minut). Błąd tego modułu nie blokuje bota głównego.

## Aplikacja na telefon i komputer
Strona jest aplikacją PWA: ma manifest, ikony i service worker, który pokazuje ostatnie dane także offline. Szczegóły personalizacji i budowania APK/MSIX są w `PERSONALIZACJA.md`.
