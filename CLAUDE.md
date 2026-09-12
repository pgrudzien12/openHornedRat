# Warhammer: Shadow of the Horned Rat — reverse engineering / open-source engine

## Cel projektu

Rozgryzienie formatów plików gry **Warhammer: Shadow of the Horned Rat** (Mindscape,
1995) w celu docelowego napisania własnego, otwartego silnika/viewera zdolnego
odtworzyć assety (i być może samą grę), na wzór projektów typu OpenMW (Morrowind)
czy OpenRA (Command & Conquer).

## Skąd się to wzięło

Właściciel gry (kupionej na GOG) próbował uruchomić ją na Linuksie przez Proton/Wine.
Po serii napraw (kompatybilność Windows XP, wirtualny pulpit zamiast fullscreen,
brakująca 32-bitowa biblioteka FreeType) gra dochodziła do menu i pierwszej misji,
ale: **brak dźwięku** (silnik audio gry emuluje sprzętowo starą kartę AWE32/MIDI,
co nie ma szans zadziałać pod żadnym Wine) oraz **losowe zamykanie się bez błędu**
po pierwszej misji (znany, udokumentowany na forum GOG, nierozwiązany bug tej wersji
pod Wine). Próba użycia **BoxedWine** (emulator x86 + własny Wine, działający jako
WebAssembly w przeglądarce) też utknęła — jego prosty "mounter" zipów jako system
plików ma jakiś błąd/ograniczenie przy dużej liczbie plików/duplikatach nazw
różniących się wielkością liter, którego nie udało się obejść.

W tym momencie, mając wolny czas, zamiast dalej łatać Wine, zaczęliśmy zamiast tego
**rozgryzać własne formaty plików gry** — pierwszy krok w stronę fanowskiego silnika
open source, tak jak robiły to inne projekty tego typu.

Instalacja gry (GOG v1.0) leży w prefiksie Wine:
```
~/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/
```
(ten prefiks służy też jako źródło danych do dalszej pracy — pliki `.BOP`/`.FOL`/`.PAL`
w `FILE/BINARY/`, `UPDATE/BINARY/`, `REMOTE/BINARY/`).

## Stan na teraz

Zobacz **`FORMATS.md`** — pełny, szczegółowy opis rozgryzionych i nierozgryzionych
formatów. W skrócie:

| Format | Status |
|---|---|
| `.PAL` (paleta kolorów) | ✅ W pełni rozgryzione: 2 warianty, paleta RGB (`STANDARD`) albo mapy kolorów 4→8 bit sprite'ów (po 512 B) |
| `.FOL` (nagłówki klatek) | ✅ W pełni rozgryzione |
| `.BOP` nieskompresowane (tła) | ✅ W pełni rozgryzione, zweryfikowane wizualnie |
| `.BOP` skompresowane (sprite'y) | ✅ 4 bpp + RLE zer, mapa kolorów w `.PAL` sprite'a; zweryfikowane wizualnie na 7279 klatkach |
| `.BTS` (bitwa), `.MRC` (armia) | ✅ Tekstowe skrypty w stylu INI. Składnia rozgryziona, parser działa na 87/87 plików, układ bitwy zweryfikowany nałożeniem na mapę planu. Część pól (cele misji, `whoami`, część `setstats`) wciąż ma nieznane znaczenie |
| `SCRIPT/*.DLL` (logika misji) | 🟡 Prawdziwe DLL Win32 (MSVC), eksportują `DLLGetScriptPointer`/`DLLReturnInstCount`. Wymagają dizasemblacji |
| `MESH/*/*.PBX`, `GRND.GD` | 🟡 PBX = kompresja RNC ProPack (metoda 2) z plikami `.gif`/`.bop` w środku, GD = siatka floatów (teren?). Niezbadane dokładnie |
| `.sbk`, `.FON` | ❌ Niezbadane |

## Struktura repo

Repo na GitHubie: https://github.com/pgrudzien12/openHornedRat (prywatne).
`samples/` i `battles/` są w `.gitignore`: to dane wyciągnięte z gry, trzymane tylko lokalnie.

```
README.md          - opis projektu (cel, wymagana oryginalna gra, gdzie ją kupić)
CLAUDE.md          - ten plik
FORMATS.md         - szczegółowa dokumentacja formatów, hipotezy, co dalej
ROADMAP.md         - plan prac: inwentarz plików gry, fazy 0-5, kamienie milowe, kolejność kroków
scripts/           - parsery/renderery napisane w trakcie analizy
  parse_pal.py     - parsuje .PAL, weryfikuje sekwencyjność indeksów
  render_pal.py    - renderuje .PAL jako obrazek PPM (pasek kolorów)
  render_bop_raw.py- dekoduje i renderuje nieskompresowany .BOP (tła) do PPM, uzywajac .FOL+.PAL
  render_sprites.py- dekoder wszystkich typow klatek .FOL/.BOP (8bpp, 4bpp, 4bpp+RLE) -> arkusz PNG
  whscript.py      - parser .BTS/.MRC: drzewo, typowany widok (JSON), walidacja licznikow (--check)
  render_battle.py - mapa bitwy z gory (granice, obiekty, sceneria, jednostki, wezly) na tle mapy planu
  battle_atlas.py  - atlas N losowych bitew kampanii: PNG + opis .md kazdej bitwy + README z legenda
  rle_v2.py        - PRZESTARZALE: stare, bledne proby dekodera RLE (trojki/dwie warstwy)
battles/           - [lokalnie, poza gitem] wygenerowany atlas 20 bitew (battle_atlas.py, ziarno 1995);
                     zawiera mapy z plikow gry, NIE dystrybuowac
samples/           - [lokalnie, poza gitem] rendery z plikow gry, NIE dystrybuowac
  standard_pal.png - zrenderowana paleta STANDARD.PAL (dowod ze .PAL jest rozgryzione)
  back1.png        - zrenderowane tlo BACK1.BOP (dowod ze nieskompresowany .BOP jest rozgryziony)
  eshin.png        - 24 klatki skrytobojcow Eshin (dowod ze skompresowane sprite'y sa rozgryzione)
  sparkle.png      - SPARKLE: 5 klatek iskierki + 8 klatek balwana (dwie mapy kolorow)
  bf001_battle.png - uklad bitwy BF001.BTS nalozony na MAP001 (dowod ukladu wspolrzednych, os Y odwrocona)
  identifiers.txt  - 1006 czytelnych identyfikatorow (CamelCase) wyciagnietych z
                     WHSHR.EXE i GAMEF.DLL - slownik nazw jednostek/zaklec/budynkow/bannerow
```

## Jak kontynuować

1. ~~Dekompresja sprite'ów~~ — zrobione (4 bpp + RLE zer, patrz `FORMATS.md`).
   Drobne otwarte kwestie opisane są tam w sekcji „Otwarte kwestie” (SPELLS.PAL ma 43 mapy,
   nietypowe rekordy HALBERD/ICON2/SPRITE3.FOL, układ kierunków animacji).
2. ~~Składnia `.BTS`/`.MRC`~~: zrobione (`scripts/whscript.py`, opis w `FORMATS.md`).
   Kolejne kroki, do wyboru:
   - rozpakować RNC w `MESH/*/*.PBX` (tekstury/sprite'y bitwy) i rozgryźć `GRND.GD` (teren 3D?);
   - zdizasemblować jeden mały `SCRIPT/BFxxx.DLL` (np. w Ghidrze), żeby zobaczyć, jak
     skrypt misji korzysta z węzłów (`NODES`) i `set:script=N` jednostek;
   - powiązać nazwy z `troopsprites`/`banner`/`loadfurn` z plikami `.FOL/.BOP`.
3. Dawny plan (dla kontekstu): zbadać `.MRC` (prawdopodobnie mapy/misje) i `.BTS`/
   pliki `script/*.dll` (prawdopodobnie logika bitew/dialogi) — to potrzebne żeby
   w ogóle wiedzieć, JAK rozstawić sprite'y na mapie, a nie tylko jak je narysować.
3. Dopiero potem sensowne stałoby się pisanie właściwego "silnika" (np. w Pythonie
   z pygame na start, jako viewer/prototyp, później ewentualnie coś wydajniejszego).

## Ważne zasady pracy w tym projekcie

- To jest projekt **hobbystyczny/eksploracyjny reverse-engineeringu**, nie klon
  komercyjny — cel to zrozumienie formatów i (być może kiedyś) fanowski viewer/silnik
  do własnej, legalnie posiadanej kopii gry. Nie dystrybuować plików gry ani danych
  z niej wyciągniętych.
- Weryfikuj hipotezy **wizualnie** gdy się da (renderuj obrazek, porównaj z tym,
  co sensowne dla gry z 1995) — samo "zgadza się liczba bajtów" bywa mylące
  (patrz: 3/13 klatek "zgadzało się" przez przypadek przy błędnej hipotezie RLE).
- Pliki gry (`.BOP`, `.PAL`, itd.) nie są w tym repo (to własność GOG/Games Workshop) —
  skrypty w `scripts/` przyjmują ścieżkę do zainstalowanej gry jako argument.
