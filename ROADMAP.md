# Roadmap — od formatów plików do otwartego silnika

Cel końcowy: silnik/viewer, który czyta pliki z **legalnie posiadanej instalacji** gry
(jak OpenMW/OpenRA) i nigdy nie zawiera ani nie dystrybuuje jej zasobów.

Oznaczenia: **S** = godziny, **M** = 1–3 wieczory, **L** = tygodnie.
✅ zrobione, 🟡 częściowo, ⬜ do zrobienia. Szczegóły formatów: `FORMATS.md`.

## Mapa terenu — co jest w instalacji

| Obszar | Pliki | Rozmiar | Status | Rodzaj |
|---|---|---|---|---|
| Sprite'y, tła, mapy planu | `BINARY/*.FOL/.BOP/.PAL` | 21 MB | ✅ | własny, rozgryziony |
| Skrypty bitew i armii | `SCRIPT/*.BTS/.MRC`, `SAVE/*.MRC/.dbf` | 1,6 MB | ✅ składnia / 🟡 semantyka | tekst INI |
| Logika misji | `SCRIPT/BFxxx.DLL` (45) | 1,1 MB | ⬜ | kod x86, dizasemblacja |
| Teren i zasoby 3D bitwy | `MESH/*/GRND.GD`, `*.PBX` | 25 MB | 🟡 rozpoznane | GD własny, PBX = RNC ProPack |
| Muzyka | `MUSIC/*.MID` + `SOUND/WARINTR3.SBK` | 1,5 MB | ⬜ | **standard**: MIDI + SoundFont 2 |
| Efekty i mowa | `SOUND/**/*.WAV` (96), `GLUE/SPEECH/*.WAV` (567), `*.SFX` (18) | 128 MB | ⬜ | WAV standard, SFX = `RIFF MSFX` własny |
| Filmy/przerywniki | `REMOTE/BINARY/ANIM/*.SI/.SR/.SM/.SN` (4×30) | 135 MB | ⬜ | Mindscape Omni `MxSt` (jak LEGO Island) + Smacker |
| UI, teksty, kursory | `DLL/BITMAP.DLL`, `*TXT.DLL`, `WND.DLL`, `GMCUR.DLL` | 11 MB | ⬜ | **standard**: zasoby PE |
| Czcionki, palety UI | `*.FON`, `GLUE/*.PAL` | 0,6 MB | ⬜ | FON = zasób Windows; PAL znany |
| Tablica `SPRITE3.BTP` | 1 plik | 64 KB | ⬜ | 256×256, hipoteza: LUT przezroczystości/cienia |
| Zapisy gry | `SAVE/savegame.0/.5` | 0,4 MB | ⬜ | własny binarny |
| Reguły gry, interpreter skryptów | `WHSHR.EXE`, `GAMEF.DLL` | 0,9 MB | ⬜ | kod x86, dizasemblacja |

`UPDATE/BINARY` to pełna kopia `FILE/BINARY` z poprawkami (288 par), która **ma pierwszeństwo**.

---

## Faza 0 — porządek w narzędziach (S–M)

Po co: każdy następny krok korzysta z tych samych ścieżek, dekoderów i testów.

- ⬜ `git init` + `.gitignore` (bez plików gry i wyciągniętych zasobów).
- ⬜ Pakiet `whshr/` zamiast luźnych skryptów: `paths.py` (szukanie bez wielkości liter,
  **UPDATE przed FILE**), `image.py` (PNG, palety), `sprites.py` (FOL/BOP), `script.py` (BTS/MRC).
  Obecne `scripts/*.py` stają się cienkimi CLI.
- ⬜ `whshr check` jako test regresji: dekoduje **wszystkie** pliki każdego znanego formatu
  (dziś: 8354 klatki, 87 skryptów) i porównuje liczniki.
- ⬜ `whshr extract <instalacja> <cache>`: konwersja do otwartych formatów (PNG/JSON/WAV)
  w katalogu poza repo, żeby przeglądać zasoby bez skryptów.

## Faza 1 — reszta zasobów 2D, tekstów i dźwięku (głównie formaty standardowe)

| # | Zadanie | Rozmiar | Weryfikacja |
|---|---|---|---|
| 1.1 | Zasoby PE z `DLL/*.DLL` (bitmapy, tablice stringów, dialogi, kursory) przez `pefile`/`wrestool` | S | obrazki UI i teksty misji wyglądają sensownie |
| 1.2 | Muzyka: `.MID` + `WARINTR3.SBK` (SoundFont 2) przez FluidSynth → OGG | S | słychać muzykę z oryginalnym brzmieniem AWE32 |
| 1.3 | `.SFX` (`RIFF MSFX`): powiązanie ID efektów z plikami WAV | M | dźwięki pasują do nazw (`BUTTONFX`, `Battle2`) |
| 1.4 | **Nazwy → pliki sprite'ów**: `troopsprites`/`banner`/`loadfurn`/`loadspr` → `.FOL` (tabele w `GAMEF.DLL`/`BITMAP.DLL`? `identifiers.txt`) | M | `render_battle` rysuje prawdziwe sprite'y zamiast kropek |
| 1.5 | Układ animacji: kierunki × klatki × akcje (chód, atak, śmierć), hotspoty z `.FOL` | M | poprawne animacje w arkuszu z podpisami |
| 1.6 | `.FON` i palety `GLUE` (menu, mapa kampanii) | S | wyrenderowany tekst menu |
| 1.7 | `SPRITE3.BTP` (hipoteza LUT 256×256) | S | podgląd jako obraz 256×256, test mieszania kolorów |
| 1.8 | Semantyka pól skryptów: `Objective:L,a,b`, `set:map`, `whoami`… (może się wyjaśnić przy tekstach z 1.1) | M | opis celów zgadza się z odprawą w grze |

**Kamień milowy M1: przeglądarka zasobów.** Sprite'y z animacjami, mapy, teksty, muzyka i dźwięki w jednym narzędziu.

## Faza 2 — bitwa w 3D (zasoby własne)

| # | Zadanie | Rozmiar | Weryfikacja |
|---|---|---|---|
| 2.1 | Dekompresor **RNC ProPack metoda 2** (znany algorytm) + lista plików w `.PBX` | M | wypakowane `.gif`/`.bop` dają się wyrenderować |
| 2.2 | `GRND.GD` (8192 × 24 B, floaty): siatka terenu, wysokości, UV/materiały? | M | mapa wysokości zgadza się z mapą planu (rzeka nisko, klify) |
| 2.3 | Teksturowanie terenu (`GRND.PBX`) i ustawienie scenerii/jednostek z `.BTS` na terenie | M | render podobny do zrzutu z gry |
| 2.4 | Kamera i oświetlenie (`Camera`, `CameraEdge`, `Bank angle`); zachowanie Reality Lab 2.0 tylko jako punkt odniesienia | M | kadry jak w grze |

**Kamień milowy M2: statyczny viewer bitwy 3D.** Dowolna `BFxxx`: teren, sceneria, oddziały na pozycjach startowych.

## Faza 3 — przerywniki i mowa (REMOTE)

| # | Zadanie | Rozmiar | Weryfikacja |
|---|---|---|---|
| 3.1 | Kontener `.SI` (`RIFF MxSt`): skorzystać z dokumentacji formatu SI z projektu dekompilacji LEGO Island (ten sam silnik Mindscape Omni) | M | wyciągnięte strumienie `.smk` |
| 3.2 | Odtwarzanie Smacker (`ffmpeg` obsługuje `.smk`) | S | film się odtwarza |
| 3.3 | `.SR/.SM/.SN`: skrypty scen (kolejność ujęć, dźwięk, napisy?) | M | sceny składają się w całość jak w grze |
| 3.4 | Powiązanie 567 nagrań mowy z tekstami i scenami | M | właściwa kwestia do właściwego portretu |

## Faza 4 — logika gry (najtrudniejsza; dizasemblacja)

Narzędzie: Ghidra (32-bit PE, MSVC 1995). Kolejność od najmniejszego ryzyka:

| # | Zadanie | Rozmiar |
|---|---|---|
| 4.1 | Interfejs DLL misji: co zwraca `DLLGetScriptPointer`/`DLLReturnInstCount`, jakie API gry wołają skrypty (na małym `BF001.DLL`) | M |
| 4.2 | W `GAMEF.DLL`: interpreter poleceń `.BTS/.MRC` i język „glue” kampanii (`testobjective`, `debrief`, `addcash`…) | L |
| 4.3 | Reguły walki: jak `s_move`, `s_armr`, `psy_status`, szeregi i morale wchodzą do obliczeń (porównywać z zasadami bitewnego Warhammera 4. ed.) | L |
| 4.4 | Zapis gry `savegame.0/.5` + przepływ kampanii (`ARMY/MARCH/PLAY.MRC`, `debrief.dbf`, złoto, najemnicy) | M–L |
| 4.5 | Przepisanie 45 skryptów misji na własny, czytelny format (DSL/Python/Lua) | L, rozkłada się w czasie |

Alternatywa wspierająca: **instrumentacja pod Wine** (logowanie wywołań API skryptów w trakcie gry)
do potwierdzania hipotez z Ghidry.

## Faza 5 — silnik

- **Narzędzia i ekstrakcja**: zostają w Pythonie (pakiet `whshr/`).
- **Prototyp**: Python + pygame (2D: mapa planu + sprite'y) jako szybki poligon dla ruchu,
  animacji i kolizji z `OBJECTS`/`BOUNDARIES`. Nie wymaga jeszcze fazy 2.
- **Docelowo**: silnik czytający instalację gry w locie, np. C++/SDL2 + OpenGL albo Godot
  (GDExtension do czytania formatów). Decyzję podjąć po M2, gdy będzie wiadomo, ile 3D
  naprawdę potrzeba.

Kamienie milowe:
- **M3**: oddziały chodzą po mapie (pathfinding z `Nav*`, kolizje), animacje kierunkowe.
- **M4**: walka i morale według reguł z 4.3, porównane z oryginałem pod Wine.
- **M5**: jedna grywalna misja (`BF001`) z ręcznie przepisanym skryptem.
- **M6**: kampania (armia między bitwami, odprawy, zapis gry).

---

## Proponowana kolejność najbliższych kroków

1. **Faza 0** (git, pakiet, `check`, `extract`), bo każdy dalszy krok na tym zyskuje.
2. **1.2 muzyka** jako szybka wygrana: oryginalna ścieżka z SoundFontu, czyli dokładnie to, czego brakowało pod Wine.
3. **1.4 + 1.5 sprite'y jednostek i animacje**, żeby `render_battle` pokazywał prawdziwe oddziały.
4. **1.1 teksty z DLL**, które pewnie wyjaśnią cele misji (1.8).
5. **2.1 + 2.2 RNC i teren**, prowadzące do M2.
6. Dizasemblację (faza 4) zacząć dopiero przed M4/M5, najpierw punktowo pod konkretne pytania.

## Ryzyka i zasady

- **Prawo**: repo zawiera tylko kod i opisy. Zasoby i wyciągnięte pliki trzymać poza repo.
  Rendery w `samples/` i atlas `battles/` powstały z danych gry, więc są w `.gitignore`
  i istnieją tylko lokalnie.
- **Weryfikacja wizualna/słuchowa** każdej hipotezy, a nie „zgadza się liczba bajtów”.
- **Mowa i filmy** to największa objętość danych (263 MB), ale najmniej istotna dla
  grywalności. Mogą poczekać.
- **Logika w natywnych DLL** to główne ryzyko projektu. Bez niej będzie „viewer”, a nie „gra”.
