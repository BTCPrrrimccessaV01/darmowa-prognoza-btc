# Personalizacja

## Adres strony
Po wgraniu do GitHub Pages adres ma postać https://TWOJA-NAZWA.github.io/darmowa-prognoza-btc/. Wpisz go w `Windows/adres.txt` i w PWABuilder.

## Nazwa, kolory, ikony
- `manifest.webmanifest`: name, short_name, theme_color, background_color.
- `index.html`: tytuł strony i kolory w CSS (tło #0b0f14, akcent #2563eb).
- `icons/icon-192.png` i `icons/icon-512.png`: podmień na własne PNG o tych samych nazwach i rozmiarach. Treść trzymaj w środkowych 80%, bo system przycina ikonę.

## Portfele
`bot.py`, lista `WAL`. Po zmianie uruchom workflow ręcznie. Historia zmian dotyczy nowych adresów od tego momentu.

## Progi alertów
`bot.py`, funkcja `alerts()`: zakres świecy powyżej 2,5× normy, przewaga od 60% lub poniżej 40%, odległość od strefy 1d poniżej 0,5%.

## Spekulacja 0,33%
`spec033.py`: `THR = 0.0033` to poziom, `W = 12` to okno w godzinach. Zmiana progu nie kasuje starych danych w `data/spec033/`, więc stare wyniki zostają z poprzednim progiem.

## Telegram
W Settings → Secrets and variables → Actions dodaj `TG_TOKEN` i `TG_CHAT`.

## Android (APK lub AAB)
1. Wejdź na pwabuilder.com i wklej adres strony.
2. Package for stores → Android → Generate. Pobierz APK do ręcznej instalacji albo AAB do Google Play.
3. Zapisz plik klucza podpisu i hasło. Bez nich nie wydasz aktualizacji tej samej aplikacji.
4. PWABuilder poda plik `assetlinks.json`. Wgraj go do repo jako `.well-known/assetlinks.json`. Bez tego aplikacja pokaże pasek adresu.
5. Na telefonie zezwól na instalację z tego źródła (Ustawienia → Zabezpieczenia).

## Windows (MSIX)
PWABuilder → Windows → Package → pobierz `.msix`. Pakiet z PWABuilder jest podpisany certyfikatem, który trzeba zainstalować jako zaufany. Wygodniej jest wgrać go do Microsoft Store, gdzie konto deweloperskie dla osób indywidualnych jest darmowe.

## Launcher Windows
`Windows/Uruchom-Prognoze.bat` otwiera stronę w oknie aplikacji Edge lub Chrome, bez paska adresu. Adres czyta z `Windows/adres.txt`.
