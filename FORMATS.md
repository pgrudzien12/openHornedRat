# Formaty plików — Warhammer: Shadow of the Horned Rat (1995, Mindscape)

Notatki z reverse-engineeringu formatów danych gry, robione czarną skrzynką
(analiza bajtów + weryfikacja wizualna), bez dizasemblacji `GAMEF.DLL`.

Gra jest zainstalowana (wersja GOG v1.0) w prefiksie Wine:
```
~/snap/steam/common/.local/share/Steam/steamapps/compatdata/3605483607/pfx/drive_c/GOG Games/Warhammer - Shadow of the Horned Rat/WARFB/
```
Dane gry leżą w `FILE/BINARY/`, `UPDATE/BINARY/` (patch nadpisujący pliki z `FILE`) i `REMOTE/BINARY/` (multiplayer?).

## `.PAL` — dwa różne formaty pod tym samym rozszerzeniem

**W pełni rozgryzione i zweryfikowane wizualnie.**

| Wariant | Przykłady | Jak rozpoznać | Liczba w `FILE/BINARY` |
|---|---|---|---|
| **A. Paleta RGB** | `STANDARD`, `NIGHT`, `BKMOUNT`, `PANEL`, `RICH` | pierwszy bajt co 4 bajty rośnie o 1 | 9 |
| **B. Mapa kolorów 4→8 bit** sprite'a | `ESHIN`, `SPARKLE`, `BAN*`, `AMBWIZ`… | rozmiar = wielokrotność 512, obok leży `.FOL` o tej samej nazwie | 141 |

(1 plik nie pasuje do żadnego wariantu, do sprawdzenia.) Uwaga: rozmiar to za mało,
żeby je rozróżnić, bo np. `ESHIN.PAL` (2048 B) jest też wielokrotnością 4.
Pewne rozróżnienie daje sekwencyjność indeksów albo typ klatki w `.FOL`.

### Wariant A — paleta RGB

Patrz `samples/standard_pal.png`.

- Brak nagłówka. Dane zaczynają się od razu.
- Rekordy po **4 bajty**: `[indeks: u8][R: u8][G: u8][B: u8]`.
- Indeksy są **sekwencyjne** i pokrywają zakres **10–245** (236 wpisów, 236×4 = 944 bajtów
  dla `STANDARD.PAL`). To pasuje do klasycznego triku GDI z Windows 3.x/95: system
  rezerwuje indeksy 0–9 i 246–255 dla kolorów systemowych, aplikacja dostaje tylko
  środkowe 236.
- Palety częściowe nie muszą zaczynać od 10: `PANEL.PAL` ma indeksy 106–245,
  `RICH.PAL` 10–33, `HALBERD.PAL` 0–15. Rozmiar pliku zawsze jest wielokrotnością 4,
  a pierwszy bajt rekordu to indeks. Wpis nadpisuje dany indeks palety systemowej.
- Główną paletą dla sprite'ów i teł w bitwie jest `STANDARD.PAL`.

Parser: `scripts/parse_pal.py`, renderer: `scripts/render_pal.py`.

### Wariant B — mapa kolorów sprite'a (4 bpp → indeksy 8-bit)

Plik to ciąg **map po 512 bajtów**, bez nagłówka; liczba map = `rozmiar / 512`.
Każda mapa ma 256 wpisów po 2 bajty i jest indeksowana **całym spakowanym bajtem**
(dwoma pikselami naraz), a nie pojedynczym nibble'em:

```c
struct ColorMap {                 // 512 bajtów
    struct { uint8_t left, right; } entry[256];
};
// piksele z bajtu b:  left = entry[b].left  (kolor nibble'a b>>4)
//                     right = entry[b].right (kolor nibble'a b&15)
```

Wartości to indeksy do `STANDARD.PAL`. W praktyce tabela jest „rozwinięciem”
16-kolorowej mapy `m[0..15]`: `entry[b] = (m[b>>4], m[b&15])`, a `m[0] = 0` oznacza
przezroczystość. Nieużywane nibble mają wartość wypełniacza (np. `0xcf`).
Zapewne chodziło o szybkość: jeden lookup na bajt zamiast dwóch na piksel.

Początek `SPARKLE.PAL` (mapa 0, więc `m = [00, 6a, 6b, 6c, cf, cf, …]`):
```
0000: 00 00 00 6a 00 6b 00 6c 00 cf 00 cf ...   entry[0x00..0x0f] = (m[0], m[n])
0020: 6a 00 6a 6a 6a 6b 6a 6c 6a cf ...         entry[0x10..0x1f] = (m[1], m[n])
```

Numer mapy dla danej klatki zapisany jest w `.FOL` (górny nibble `flags[0]`, patrz niżej).
Różne mapy tego samego sprite'a to zapewne warianty kolorystyczne (np. barwy
pułku albo szkoły magii), a jedna mapa może też służyć innej grupie klatek
(`SPARKLE`: mapa 0 to iskierka, mapa 1 to bałwan).

## `.FOL` — tablica klatek/obiektów (Frame Object List?)

**W pełni rozgryzione.**

Tablica rekordów **po 16 bajtów** każdy (liczba klatek = `rozmiar_pliku / 16`):

```c
struct FolEntry {
    int16_t hotspot_x;   // offset 0, prawdopodobnie punkt zaczepienia sprite'a
    int16_t hotspot_y;   // offset 2
    int16_t width;       // offset 4
    int16_t height;      // offset 6
    uint32_t bop_offset; // offset 8, offset danych tej klatki w odpowiadającym .BOP
    uint8_t  kind;       // offset 12: dolny nibble = typ klatki (1/2/4, patrz .BOP),
                         //            górny nibble = numer mapy kolorów w .PAL (typy 2 i 4)
    uint8_t  unk13;      // offset 13: 02 lub 04, znaczenie nieznane
    uint8_t  unk14;      // offset 14: 00 lub 04, znaczenie nieznane (04 czesto przy 4 bpp)
    uint8_t  unk15;      // offset 15: zawsze 40 w typowych plikach
};
```

Najczęstsze wartości `flags` (bajty 12–15) we wszystkich `.FOL`:
`04 02 04 40` (4420 klatek), `24 02 04 40` (3716), `34 02 04 40` (3380), `14 02 04 40` (1408),
`01 04 00 40` (688), `02 02 04 40` (618), `01 02 04 40` (418), `01 02 00 40` (412),
dalej `44..f4 02 04 40` (głównie `SPELLS`).

- Segment klatki w `.BOP` zaczyna się w `bop_offset` i kończy na następnym
  **większym** offsecie z tego pliku (albo na końcu pliku). Klatki nie muszą być
  ułożone po kolei, a 2 klatki współdzielą offset, dlatego trzeba sortować
  unikalne offsety.
- Wyjątki: `HALBERD.FOL`, `ICON2.FOL`, `SPRITE3.FOL` mają inny układ bajtów 12–15
  (wartości rosną jak liczniki). Patrz „Otwarte kwestie”.

Każdy `.FOL` ma parę o tej samej nazwie: `.BOP` z rzeczywistymi danymi pikseli.

Przykład: `SPARKLE.FOL` (208 bajtów = 13 klatek animacji), każda klatka 32×32,
`bop_offset` rośnie nierówno między klatkami (bo dane w `.BOP` są skompresowane
i mają zmienny rozmiar).

## `.BOP` — dane pikseli (Bitmap Of Pixels?)

**W pełni rozgryzione i zweryfikowane wizualnie.**

`.BOP` nie ma nagłówka: to po prostu sklejone segmenty klatek, adresowane z `.FOL`.
Sposób odczytu segmentu zależy od typu klatki (`kind & 0x0F`):

| Typ | Dane w segmencie | Rozmiar segmentu | Kolory | Przykłady | Weryfikacja |
|---|---|---|---|---|---|
| `1` | surowe **8 bpp** | `w × h` | wprost indeksy `STANDARD.PAL` | tła `BACK*`, portret `DWA4`, `ICONS` | `samples/back1.png` |
| `2` | surowe **4 bpp** (2 piksele/bajt) | `ceil(w/2) × h` | mapa z `.PAL` | duży sztandar `BANWBRI` klatka 0 | render sztandaru Bright Wizard |
| `4` | **4 bpp + RLE zer** | zmienny | mapa z `.PAL` | jednostki, efekty, zaklęcia, małe sztandary | `samples/eshin.png`, `samples/sparkle.png` |

Wszystkie wiersze biegną od góry do dołu, piksele od lewej do prawej, bez paddingu
wiersza poza zaokrągleniem `ceil(w/2)` przy 4 bpp. Przy nieparzystej szerokości
ostatni nibble wiersza jest pomijany (9 takich klatek, dekodują się poprawnie).
Indeks koloru 0 = przezroczysty.

Weryfikacja na wszystkich 288 parach `.FOL`/`.BOP` z `FILE/BINARY` (8354 klatki):
- typ 4: każda z 7279 klatek rozpakowuje się do dokładnie `ceil(w/2) × h` bajtów
  i trafia na `00 00` dokładnie na końcu swojego segmentu;
- typy 1 i 2: rozmiar segmentu = `w × h` albo `ceil(w/2) × h`;
- renderingi: skrytobójcy Eshin (kilka kierunków), pociski ognia i kule ognia
  z `SPELLS` w kilku obrotach, portret krasnoluda z klatkami ust (`DWA4`), sztandar
  `BANWBRI`, iskierka i bałwan z `SPARKLE`.

Implementacja referencyjna: `scripts/render_sprites.py`.

### Kompresja (typ 4)

Najpierw obraz jest pakowany do 4 bpp: górny nibble to lewy piksel, dolny prawy,
wiersze mają `ceil(w/2)` bajtów. Potem powstały strumień bajtów jest kompresowany
**tylko z zer** (0 = przezroczysty), liniowo przez całą klatkę, bez granic wierszy:

```
00 NN   -> NN bajtów 0x00 (NN = 1..255, dłuższe przerwy = kilka par)
00 00   -> koniec klatki
XX      -> (XX != 0) jeden bajt literalny = dwa piksele
```

Przykład, `SPARKLE` klatka 0 (32×32, czyli 512 bajtów spakowanych):
`00 f8 | 30 | 00 ff | 00 08 | 00 00` = pominięte 248 bajtów, bajt `30` (piksel
koloru 3 w (16,15), środek), pominięte 255+8, koniec. 248+1+255+8 = 512.

Uwagi:
- Bajt literalny nigdy nie jest `00`, więc bajt z dwoma przezroczystymi pikselami
  zawsze idzie jako `00 01`. Bajt z jednym przezroczystym pikselem (np. `30`)
  jest zwykłym literałem.
- Przerwy nie są wyrównane do wierszy: jedna para `00 NN` może przejść przez koniec
  wiersza (np. „resztę tego wiersza + początek następnego”).
- Encoder dzielił przerwy dłuższe niż 255 na kilka par (`00 ff 00 08`).

Wcześniejsza hipoteza „trójek skip/count/color i dwóch warstw” była błędna:
dane czytano jako piksele 8-bitowe, więc pary `00 NN` wyglądały jak trójki,
a nadmiar bajtów jak druga warstwa. Segment nie ma warstw.

### Mapa kolorów

Typy 2 i 4 zamieniają bajty na indeksy palety mapą nr `kind >> 4` z pliku
`<NAZWA>.PAL` (wariant B, opisany wyżej przy `.PAL`). Przykłady:
- `SPARKLE.PAL`: 2 mapy. Klatki 0–4 (iskierka) mają `kind = 04`, a klatki 5–12 (bałwan) `14`.
- `ESHIN.PAL`: 4 mapy, `kind` od `04` do `34`.

### Dekoder referencyjny (pseudokod C)

```c
// wejście: seg = bop + fol.bop_offset, w/h z .FOL, cmaps = zawartość <NAZWA>.PAL
// wyjście: out[w*h] = indeksy STANDARD.PAL, 0 = przezroczysty
int type = fol.kind & 0x0F, map = fol.kind >> 4, bw = (w + 1) / 2;

if (type == 1) { memcpy(out, seg, w * h); return; }

uint8_t packed[bw * h];
if (type == 2) {
    memcpy(packed, seg, bw * h);
} else {                                   // type == 4
    uint8_t *p = packed;
    for (;;) {
        uint8_t b = *seg++;
        if (b != 0) { *p++ = b; continue; }
        uint8_t n = *seg++;
        if (n == 0) break;                 // 00 00 = koniec klatki
        memset(p, 0, n); p += n;           // 00 NN = NN bajtów zer
    }
}

const uint8_t *cm = cmaps + 512 * map;
for (int y = 0; y < h; y++)
    for (int x = 0; x < w; x++) {
        uint8_t b = packed[y * bw + x / 2];
        out[y * w + x] = cm[b * 2 + (x & 1)];
    }
```

### Otwarte kwestie

- `SPELLS.PAL` ma 43 mapy (22016 B), a nibble w `kind` sięga tylko 15. Możliwe,
  że mapę dla zaklęć wybiera kod gry (kolor szkoły magii), a flaga podaje tylko
  wartość domyślną.
- 84 klatki typu 2 należą do plików, które nie mają własnego `.PAL`. Nie wiadomo,
  skąd biorą mapę kolorów: może z pliku o innej nazwie, a może ustawia ją kod gry.
- Jeden plik `.PAL` nie pasuje ani do wariantu A, ani do B.
- Znaczenie `flags[1]` (`02`/`04`), `flags[2]` (`00`/`04`) i `flags[3]` (`40`) jest
  nieznane. Na dekodowanie nie wpływają.
- `HALBERD.FOL`, `ICON2.FOL` i `SPRITE3.FOL` mają inny układ rekordów (flagi wyglądają
  jak rosnące liczniki/offsety). Do zbadania osobno.
- Hotspot, kolejność kierunków i klatek animacji: `ESHIN` wygląda na 8 kierunków
  × N klatek, ale nie jest to jeszcze sformalizowane.
- `UPDATE/BINARY` nadpisuje `FILE/BINARY`, test objął tylko `FILE`.

## Skrypty `.BTS` (bitwa) i `.MRC` (armia), katalog `FILE/SCRIPT/`

**Składnia w pełni rozgryziona; układ bitwy zweryfikowany wizualnie** (patrz
`samples/bf001_battle.png`). Semantyka części pól jest wciąż hipotezą (zaznaczone niżej).
Parser: `scripts/whscript.py`, renderer: `scripts/render_battle.py`.

Zawartość `FILE/SCRIPT/`: 54 × `.BTS`, 33 × `.MRC` (w tym `MARCH.MRC`), 45 × `.DLL`, 1 × `.DBF`.
To **tekst**, a nie dane binarne. Pliki wygenerował edytor twórców:
- w `WHSHR.EXE`/`GAMEF.DLL` są filtry okien plików `script {*.bts}`, `mercs {*.mrc}`, `mesh {*.asc}`;
- w każdej jednostce jest komentarz `;S_RACE is Human Infantry...are you sure this is right?`,
  pochodzący z łańcucha formatu `;S_RACE is %s %s...are you sure this is right?` w EXE;
- numerowane komentarze `; unit N`, `;Collision Object N`, `;piece N`, `; Script Node N`.

Pliki testowe twórców (nie należą do kampanii): `_DESTEST`, `_KFTEST`, `RLTEST`, `RLTEST1`,
`WIZTEST`, `SPRED`, `MAXARMY`, `PLOT1`. Pliki `B` i `DB015` nie mają numeracji `BFxxx`
i używają skryptów innych bitew (`bf004_1`, `bf015`), więc ich status jest niepewny.

### Składnia (wspólna)

- ASCII/latin-1, końce linii CRLF. Wcięcia tabulatorami nie mają znaczenia.
- `;` na początku linii to komentarz. Po `[END]` też może być komentarz (`[END]\t; end of FIELD`).
- `[NAZWA]` otwiera sekcję, `[END]` zamyka najbliższą. Korzeń: `[BATTLESCRIPT]` albo `[MERCARMY]`.
- Każda inna linia to `polecenie:argument` (podział na pierwszym `:`):
  - `set:klucz=wartość`: pole liczbowe albo tekstowe; flagi łączone `|` (`os_active|os_solid`);
  - `setstats:klucz=a,b,c`: lista liczb całkowitych;
  - polecenia-flagi z pustym argumentem: `hidden:`, `DeployTroops:`, `NoBirds:`;
  - klucze ze spacjami: `Ambient light color:`, `Bank angle:`.
- Bloki (wielkość liter bez znaczenia, w plikach jest i `addunit`, i `AddBoundary`):
  `addunit…endunit`, `addleader…endleader` (wewnątrz jednostki), `addobject…endobject`,
  `addrectangles…endrectangles` (wewnątrz obiektu), `addnode…endnode`, `AddBoundary…EndBoundary`.
- W nazwach `<` i `_` zastępują spację: `Grudgebringer<Cavalry`, `Hiln's_Guard`, `Cmdr._Bernhardt`.
- Nazwy granic i ścieżki nie są znormalizowane (`Cameraedge`, `Battlefield edge`, `\bf001.mrc`,
  `\Bf012.mrc`), więc porównywać bez rozróżniania wielkości liter i szukać plików tak samo.

**Liczniki:** `set:count` w `[UNITS]`, `[SCENERY]`, `[BOUNDARIES]` i `[NODES]` oraz
`set:Lines` (suma `AddLine`) zgadzają się z zawartością w 83/87 plików. Wyjątki to tylko
pliki testowe (`ARMY.MRC`, `RLTEST.BTS/.MRC`, `SPRED.BTS`). **`[OBJECTS] set:count` nigdy
nie równa się liczbie `addobject`** (w 25/54 plików = obiekty + wszystkie jednostki,
w reszcie odchyla się o −8…+9). Silnik powinien go ignorować i liczyć bloki.

### Układ współrzędnych

- Jednostki świata. `[FIELD] set:x/y` = rozmiar pola bitwy (od 1280 do 2960 w każdej osi).
  `BattleEdge` to zwykle prostokąt odsunięty o 16 od brzegów.
- **Oś Y rośnie w górę mapy planu** (jak w matematyce, a nie jak na obrazku). Mapa planu
  (`loadplanmap`, np. `MAP001`, 196×216 px dla pola 1600×1760, skala ≈ 1:8,16 w obu osiach)
  pokrywa dokładnie całe pole. Weryfikacja na `BF001` i `BF005`: dopiero po odwróceniu Y
  okręgi kolizji leżą na drzewach i skałach, a granice biegną wzdłuż rzeki, klifów
  i skraju lasu.
- Współrzędne mogą wychodzić poza pole (`CameraEdge` sięga −300; w `BF001` kusznicy stoją
  na x=1814 przy szerokości 1600 — hipoteza: posiłki wchodzące później).
- `dir` i czwarta liczba `placefurniture` mają wartości 0…511 (maks. zaobserwowane 504).
  **Hipoteza:** pełny obrót = 512. Punkt zerowy i kierunek obrotu są niezweryfikowane.

### `.BTS` — sekcje

Kolejność w plikach: `FIELD`, `MISSIONINFO`, `DYNAMIC_LOAD`, `OBJECTS`, `SCENERY`,
`BOUNDARIES`, `UNITS` (1 albo 2 sekcje), `NODES`.

| Sekcja | Zawartość |
|---|---|
| `FIELD` | patrz tabela niżej |
| `MISSIONINFO` | `DeployTroops:` (gracz sam rozstawia wojska), `Objective:L,a,b` (litera A–Z + 2 liczby; znaczenie nieznane, najczęściej `Z` i `A`) |
| `DYNAMIC_LOAD` | zasoby do wczytania: `loadspr:Nazwa,n` (sprite'y, np. `BattleSprites`), `loadsfx:Nazwa`, `loadfurn:Typ` (typy scenerii użyte w `SCENERY`), `NoBirds:` |
| `OBJECTS` | obiekty kolizji: `set:status` (`os_active`, `os_solid`, rzadko `os_camcollide`), `x`, `y`, `z`, `radius`, `dir`. Opcjonalnie `addrectangles:=N` z `rect:x1,y1,x2,y2`, czyli prostokąty względem środka obiektu, zapewne obrócone o `dir` |
| `SCENERY` | `placefurniture:Typ,x,y,dir`: drzewa, skały, budynki. Prefiks `D_` (np. `D_SnwWatchTower`) to zapewne wariant zniszczony |
| `BOUNDARIES` | `AddBoundary:Nazwa` + `AddLine:x1,y1,x2,y2`, czyli nazwane łamane. Nazwy: `BattleEdge` (granica pola), `ViewEdge`, `SightEdge`, `CameraEdge`, `DeploymentArea`/`Merc Deployment` (strefa rozstawienia), `Nav1…NavN` (przeszkody nawigacji wzdłuż nieprzejezdnego terenu), terenowe: `CliffsEdge`, `RiverEdge`, `WallsEdge`, `Hedge`, `LakeEdge`… |
| `UNITS` | jednostki (format niżej). Etykieta z komentarza: `; Enemy Army` (54), druga sekcja `NPC units` (27) |
| `NODES` | węzły dla skryptu misji: `set:status` (`ns_active`, `ns_startpos`, `NS_END`), `x`, `y`, `radius`, `dir`, `id` (zwykle 0; też 1–13 i 99). Łańcuchy `ns_startpos` prowadzą do strefy rozstawienia. **Prawdopodobnie każdy `NS_END` to docelowa pozycja jednego oddziału gracza**: w 41/44 bitwach kampanii liczba `NS_END` = liczba oddziałów gracza, a węzłów `ns_startpos` jest zwykle kilka więcej. Ale tylko w 8/44 oddziały z `.MRC` stoją dokładnie na tych węzłach, więc pozycje w `.MRC` zwykle nie są pozycjami startowymi. 501 z 547 oddziałów gracza ma `hidden:`, co pasuje do wprowadzania armii na pole skryptem albo rozstawieniem (statystyki: `scripts/battle_atlas.py`) |

`[FIELD]`:

| Pole | Znaczenie |
|---|---|
| `set:x`, `set:y` | rozmiar pola bitwy |
| `set:map` | 17, 18, 19, 34, 35, 49, 50 — znaczenie nieznane |
| `loadmerc:\bf001.mrc` | armia gracza (`.MRC`). W 29 bitwach to plik **innej** bitwy (np. `BF006–BF008` → `bf001.mrc`), zapewne dlatego, że w kampanii armia przechodzi dalej |
| `loadmesh:bf001` | katalog `FILE/MESH/BF001/` (teren i zasoby 3D, patrz niżej) |
| `loadpal:standard` | paleta RGB: `standard`, `bkmount`, `underway`, `night` |
| `loadScript:bf001` | logika misji `FILE/SCRIPT/BF001.DLL` (pliki testowe używają `bf003`) |
| `loadplanmap:MAP001` | mapa planu, klatka 0 z `MAP001.FOL/.BOP` (typ 1, 8 bpp) |
| `loadportbg:BACK14` | tło portretów |
| `Ambient light color`, `Position`, `Bank angle` | floaty; prawie zawsze zera (w 2 plikach wartości testowe 1,2,3…) |
| `Camera:45.0` | 0/45/90/135/180/270 — zapewne początkowy obrót kamery |
| `set:vx`, `set:vy`, `set:zoom` | tylko w 1 pliku; zapewne początkowy widok |

### `.MRC` — armia

Korzeń `[MERCARMY]`, w nim `[UNITS]` (etykieta `; Mercinary Army` albo
`; Mercenary Army (Marching Orders)`) i czasem `[MISSIONINFO]` (`ARMY.MRC`, `SPRED.MRC`).
Wczytywany z `.BTS` przez `loadmerc`. `MARCH.MRC` leży i w `FILE/SCRIPT/`, i w `SAVE/`,
czyli to zapewne bieżący stan armii w kampanii.

### Jednostka (`addunit`), wspólna dla `.BTS` i `.MRC`

```
addunit:Grudgebringer<Cavalry          nazwa ('<'/'_' = spacja)
    hidden:                            opcjonalnie: ukryta na starcie (hipoteza)
    set:whoami=2                       0 dla zwykłych wrogów; 1..100 dla nazwanych jednostek (hipoteza: stałe ID w kampanii)
    set:hired=0                        0/1: najemnik opłacony (hipoteza)
    troopsprites:BorderHorse,0         nazwa zestawu sprite'ów (identyfikator, patrz identifiers.txt)
    banner:BannerMrcCmdr,0             sztandar
    addmagicitem:ItemGrudgeBringer     0..n
    addspell:AmberTanglingThorn        0..n (magowie)
    set:psy_status=HateSkaven|CantBreak  psychologia z zasad bitewnych, patrz niżej
    setstats:s_side=2,12,12,4          patrz niżej
    setstats:s_move=4,4,3,3,3,1,3,1,7  profil M WS BS S T W I A Ld
    setstats:s_mount=1,13,3,16,13,0    s_mount[0] = 1 dla kawalerii, 0 dla piechoty; reszta nieznana
    setstats:s_weap=3  S_BalWeap=0  s_pntval=13  s_cmdr=0,0,4,0  s_armname=0,4   (nieznane dokładnie; s_pntval ≈ wartość punktowa)
    setstats:s_armr=5                  pancerz (tylko przy części jednostek i dowódców)
    setstats:s_rlmv=…  s_lead=…        rzadkie (6 jednostek, 9 liczb)
    set:s_calualties=0 s_routed=0 s_kills=0 s_Exp=0   stan/doświadczenie w kampanii
    ;S_RACE is Human Cavalry...are you sure this is right?
    addleader:Cmdr._Bernhardt          opcjonalny dowódca
        leaderportrait:Commander,0     (VoidType,0 = bez portretu)
        troopsprites:… setstats:s_move=… s_armr=… s_weap=… s_armname=…
    endleader:
    set:dir=0  set:x=1097  set:y=645
    set:script=PLAYER_SCRIPT           albo liczba (0..27): instancja skryptu AI z DLL misji (hipoteza, por. eksport DLLReturnInstCount)
endunit:
```

**`s_move` = profil z bitewnego Warhammera** (M, WS, BS, S, T, W, I, A, Ld). Potwierdzenie:
Clanrats `5,3,3,3,3,1,4,1,5` to dokładnie profil Clanrata z podręcznika; ludzka piechota ma `4,3,3,3,3,1,3,1,7`.

**`s_side = [typ, rozmiar, rozmiar_początkowy, ?]`.**
- `s_side[1] == s_side[2]` w 829/869 jednostek. Zgodnie z kolejnością nazw w `GAMEF.DLL`
  (`s_rnks s_size s_orgsize s_side`) to zapewne bieżąca i początkowa liczebność.
- `s_side[3]` ma wartości 1–7; hipoteza: liczba szeregów.
- `s_side[0]` to bajt bitowy. Rozkodowane przez zestawienie z komentarzami `;S_RACE is …`
  we wszystkich plikach:
  - bit 7 (`0x80`) = **strona wroga**: wszystkie Skaveny, Orki i Gobliny oraz wrogowie-ludzie (`129` = Human Infantry);
  - bit 6 (`0x40`) = zapewne strona neutralna/NPC: `RollingStock` (wozy), `Peasant`, sojusznicy;
  - bity 0–5 = typ oddziału (etykieta dominująca):

| kod | typ | kod | typ | kod | typ |
|---|---|---|---|---|---|
| 0 | potwór | 7 | Skaven (piechota/magowie/potwory) | 14 | Peasant |
| 1 | Human Infantry | 8 | Orc Infantry | 15–17 | Human Artillery |
| 2 | Human Cavalry | 9 | Orc Cavalry | 18 | Orc Artillery |
| 3 | Human Archers | 10 | Orc Archers | 19 | Human Wizard |
| 4 | Dwarven Infantry | 11 | Goblinoid (piechota, magowie, artyleria, potwory) | | |
| 5 | Dwarven Archers | 12 | Goblinoid Cavalry | | |
| 6 | Elven | 13 | Goblinoid Archers | | |

  Komentarz S_RACE nie zawsze zgadza się z kodem (np. kod 3 bywa „Human Cavalry”).
  Edytor najwyraźniej wyliczał go z innego pola (`s_race`) i ostrzegał o niezgodności.

**`psy_status`** (flagi `|`): `HateGreens`, `HateSkaven`, `HateDwarfs`, `FearToGobs`,
`CauseFear`, `CauseTerror`, `Frenzy`, `CantBreak`, `CantRally`, `CantMelee`, `CantDie`,
`PsyImmune`, `MagicResistent`. To reguły psychologii z bitewnego Warhammera.

### Parser

```
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS          # podsumowanie
python3 scripts/whscript.py .../FILE/SCRIPT/BF001.BTS --json   # pełny widok (z armią z loadmerc)
python3 scripts/whscript.py --check .../FILE/SCRIPT            # wszystkie pliki + liczniki
python3 scripts/render_battle.py .../FILE/SCRIPT/BF001.BTS out.png 0.5
```

### Otwarte kwestie (skrypty)

- Znaczenie `Objective:L,a,b`, `set:map`, `whoami`, `s_side[3]`, `s_mount[1..]`, `s_cmdr`,
  `s_armname`, `s_weap`, `S_BalWeap`.
- Jak nazwy `troopsprites`/`banner`/`loadfurn`/`loadspr` mapują się na pliki `.FOL/.BOP`
  (nazwy 8.3 są inne, np. `EshinAssassin` → `ESHIN.FOL`?). Możliwe, że pośredniczy `DLL/BITMAP.DLL`.
- Punkt zerowy `dir` i czy pełny obrót to 512.
- W `WHSHR.EXE`/`GAMEF.DLL` jest też słownik innego języka skryptów (kampania/„glue”):
  `testobjective`, `debrief`, `iftrueplaymovie`, `addcash`, `unitjoinmission`, `playmidi`…
  Nie wiadomo jeszcze, w których plikach jest używany.

## Logika misji — `FILE/SCRIPT/BFxxx.DLL`

Prawdziwe biblioteki **PE32 Win32 (i386), skompilowane MSVC**, ok. 24–29 KB, w większości
runtime C. Nazwa wewnętrzna `dll.dll`. Eksporty: `DLLGetScriptPointer`, `DLLReturnInstCount`.
Gra ładuje je przez `script\%s.DLL` (komunikat `Failed to load Script DLL %s`).
Hipoteza: `DLLGetScriptPointer` zwraca tablicę funkcji AI/wyzwalaczy, a jednostki odwołują
się do nich przez `set:script=N`. **Do zbadania dizasemblacją** (np. Ghidra).
Otwarty silnik musiałby przepisać te skrypty ręcznie.

## Zasoby 3D bitwy — `FILE/MESH/<BITWA>/` (wstępne rozpoznanie)

Każda bitwa (`loadmesh`) ma katalog z plikami `GRND.GD`, `GRND.PBX`, `SCENERY.PBX`, `SPRITES.PBX`.

- **`.PBX`** zaczyna się od `RNC\x02`, czyli **Rob Northen ProPack**, metoda 2 (znany format,
  istnieją otwarte dekompresory). Między skompresowanymi bajtami widać nazwy plików
  (`s_gr4.gif`, `ENBATT.bop`), więc to spakowane tekstury i sprite'y bitwy.
- **`GRND.GD`** ma zawsze 196608 B = 8192 × rekord 24 B. Wygląda na float32 z wartościami
  rosnącymi co 10 (siatka). Hipoteza: siatka terenu. Niezbadane.

## Inne pliki (niezbadane)

- `windbk2.pal`, `windmap.pal` itd. w `binary/glue/` — dodatkowe palety UI (menu,
  mapa kampanii), format prawdopodobnie identyczny jak `.PAL` opisany wyżej.
- `.FON` (np. `GOTHTEXT.FON`, `PCTEXT.FON`) — czcionki bitmapowe UI, niezbadane.
- `.sbk` (`warintr3.sbk`) — plik dźwiękowy, prawdopodobnie format specyficzny dla
  silnika audio gry (AWE32/soundblaster), niezbadane.
- `.mid` — standardowe pliki MIDI (muzyka), prawdopodobnie bez modyfikacji formatu.
- `.avi` (`indeo.avi`) — filmik w kodeku Indeo, format standardowy.

## Słownik nazw (`samples/identifiers.txt`)

1006 unikalnych identyfikatorów CamelCase wyciągniętych przez `strings` z
`WHSHR.EXE` i `GAMEF.DLL`. To wewnętrzne nazwy programistów łączące skrótowe
nazwy plików 8.3 (np. `BANORC1`) z czytelnym znaczeniem (`BannerOrc1`), a także
pełne nazwy zaklęć, jednostek, budynków itd., których nie ma wprost w nazwach
plików na dysku. Bardzo przydatne jako punkt odniesienia przy dalszej pracy.

Przykładowe kategorie:
- Zaklęcia magów: `AmberCurseOfAnraheir`, `BrightFireball`, `CelestialLightning`,
  `CelestialStormOfShemtek`, `AmberFlockOfDoom`...
- Jednostki/postacie: `AmberWizard`, `BrightWizard`, `CelestialWizard`, `GreySeer`,
  `BlackOrcs`, `ArraBoyz`, `BigUns`...
- Budynki/teren: `AverlandKeep1`–`8`, `AngRoofHouse`, `BalconyHouse`,
  `BlackCaveEnt/Left/Mid`...
- Sztandary (frakcje): rodzina `Banner*` (Dwarf, Orc, Skaven, Empire, Elf, Troll...).
