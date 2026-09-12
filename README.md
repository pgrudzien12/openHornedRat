# openHornedRat

Otwarty, fanowski silnik do gry **Warhammer: Shadow of the Horned Rat** (Mindscape, 1995),
pierwszej strategii czasu rzeczywistego osadzonej w świecie Warhammer Fantasy.

Wzorujemy się na projektach takich jak [OpenMW](https://openmw.org) (Morrowind) czy
[OpenRA](https://www.openra.net) (Command & Conquer). Chcemy, żeby w oryginalną grę dało się
wygodnie zagrać na współczesnych systemach, w tym na Linuksie. Bez emulacji, bez Wine
i bez błędów starego silnika, takich jak brak dźwięku czy losowe zamykanie się gry.

## Stan projektu

Projekt jest na wczesnym etapie. Na razie **rozgryzamy formaty plików gry**, a nie piszemy
jeszcze właściwego silnika. W `scripts/` są parsery i renderery, które już teraz potrafią
odczytać palety, grafiki teł, sprite'y jednostek i skrypty bitew. Szczegóły:

- [`FORMATS.md`](FORMATS.md): opis rozgryzionych i nierozgryzionych formatów plików;
- [`ROADMAP.md`](ROADMAP.md): plan dalszych prac i kamienie milowe.

## Wymagana oryginalna gra

**To repozytorium nie zawiera żadnych plików z gry i nigdy nie będzie ich zawierać.**
Grafika, dźwięk, mapy i skrypty misji są własnością ich właścicieli (Games Workshop i inni).
Silnik, tak jak OpenMW czy OpenRA, będzie wczytywał assety z **Twojej legalnie kupionej
kopii gry**.

Grę można kupić na przykład tutaj:

- **GOG.com**: [Warhammer: Shadow of the Horned Rat](https://www.gog.com/en/game/warhammer_shadow_of_the_horned_rat),
  wersja bez DRM. Na tej wersji (GOG v1.0) oparte są dotychczasowe prace.
- **Steam**: [Warhammer: Shadow of the Horned Rat (Classic)](https://store.steampowered.com/app/4280870/Warhammer_Shadow_of_the_Horned_Rat_Classic/),
  wydanie z 2026 roku. Nie sprawdzaliśmy jeszcze, czy jego pliki są takie same jak w wersji GOG.

Oryginalne wydanie CD-ROM z 1995 roku też powinno działać, ale nie było testowane.

## Użycie skryptów

Skrypty przyjmują jako argument ścieżkę do zainstalowanej gry, czyli do katalogu `WARFB/`
w instalacji GOG. Wyniki, np. rendery sprite'ów, map czy atlas bitew, zapisują lokalnie.
Katalogi z takimi wynikami (`samples/`, `battles/`) są w `.gitignore`. Zawierają dane
wyciągnięte z gry, więc nie wolno ich commitować ani rozpowszechniać.

## Licencja i prawa

To projekt hobbystyczny i niekomercyjny, niezwiązany z Games Workshop, Mindscape, GOG
ani SNEG. Warhammer i Shadow of the Horned Rat są znakami towarowymi ich właścicieli.
