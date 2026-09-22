# `.PBX` containers and RNC ProPack decompression (ROADMAP 2.1)

| Item | Status |
|---|---|
| RNC ProPack method 2 decompressor (pure Python, both CRCs checked) | ✅ 133/133 files |
| `.PBX` container v2: header, embedded files, textures, meshes, directory | ✅ structure verified on all 132 v2 files |
| Embedded `.bop/.fol/.pal` files | ✅ byte-identical to `UPDATE/BINARY`, all frames decode |
| Textures (`*.gif` names, really serialized `D3DRMIMAGE`) | ✅ rendered, visually correct |
| Meshes (`*.xof` names, Reality Lab meshes) | ✅ geometry/UV/texture binding verified visually; 🟡 meaning of a few fields |
| Texture transparency and trailer fields | 🟡 hypothesis, visually plausible |
| Container v1 (`MESH/BF004/GRND.PBX`, not used by any script) | 🟡 header + textures parsed, mesh section only partly |
| RNC method 1 (Huffman) | ❌ not implemented, no game file uses it |

---

## Text for `FORMATS.md`

### `.PBX` — RNC-compressed battle resource container, `FILE/MESH/<BATTLE>/`

`FILE/MESH/` has 45 battle directories (plus empty `SCENERY/` and `TEXTURE/`): 45×`GRND.PBX`,
44×`SCENERY.PBX`, 44×`SPRITES.PBX` = 133 files. `MESH/BF004/` only has `GRND.PBX` (old format,
see v1 below). No `.BTS` loads `bf004`. `B.BTS` and `BF004_1.BTS`…`BF004_5.BTS` use `bf004_1…5`.

**File layout:** `[0x01]` (1 byte, missing only in `BF004/GRND.PBX`) + **exactly one RNC block**
covering the rest of the file (`18 + packed == file size - 1`). There is no uncompressed data and no
second block. The decompressed data is the container described below.

#### RNC ProPack header (18 bytes, big-endian)

| Offset | Type | Field |
|---|---|---|
| 0 | `char[3]` | `"RNC"` |
| 3 | `u8` | method: always `2` here |
| 4 | `u32` | unpacked size |
| 8 | `u32` | packed size (data after the header) |
| 12 | `u16` | CRC-16 of the unpacked data |
| 14 | `u16` | CRC-16 of the packed data |
| 16 | `u8` | leeway (extra bytes for in-place unpacking) |
| 17 | `u8` | number of chunks |

CRC is **CRC-16/ARC** (reflected polynomial `0xA001`, initial value 0).

#### RNC method 2 bit stream

Bits are read MSB-first from a byte. A new bit byte is fetched from the input only when the
previous one is used up. Raw bytes (literals, low byte of a distance, length byte) are read from
the same stream in between, so the order of reads matters. The stream starts with 2 skipped bits.

```
0              literal: copy 1 raw byte
10 x [1 y]     n = 4 + x; if the next bit is 1: n = 2*(n-1) + y  (6..9)
               n == 9: literal run of (4 bits)*4 + 12 raw bytes (12..72)
               else:   match of length n, distance = OFFSET
110 B          match of length 2, distance = B + 1           (B = raw byte)
1110           match of length 3, distance = OFFSET
1111 B         B != 0: match of length B + 8, distance = OFFSET
               B == 0: end of chunk, followed by 1 bit (more chunks); the bit buffer is NOT reset
OFFSET:        hi = 0
               if bit: hi = bit
                       if bit: hi = (hi<<1 | bit) | 4;  if !bit: hi = hi<<1 | bit
                       elif hi == 0: hi = bit + 2
               distance = (hi << 8 | raw byte) + 1
```

Matches copy from `out[-distance]` byte by byte (overlap allowed). Decoding stops at the
unpacked size. The end marker of the last chunk (2 bytes) is then left unread.

#### Container (after unpacking), version 2 — all fields little-endian

```c
struct PbxHeader {            // 32 bytes
    uint32_t magic;           // 0xC8457560 (bytes 60 75 45 C8)
    uint32_t version;         // 207 (0xCF) in all 132 v2 files
    uint32_t unk8;            // always 0
    uint32_t mesh_count;      // GRND: 1, SCENERY: 37..69, SPRITES: 0
    uint32_t file_count;      // SPRITES: 9..111, others: 0
    uint32_t texture_count;   // GRND: 2..11, SCENERY: 21..89, SPRITES: 0
    uint32_t texture_pixel_bytes;    // sum of w*h over all textures (verified)
    uint32_t texture_palette_bytes;  // 1024 * texture_count (verified)
};
// then, in this order, with no padding:
//   file_count    x FileRecord
//   texture_count x TextureRecord
//   mesh_count    x MeshBlob       (concatenated, in data order)
//   mesh_count    x NameRecord     (mesh names, e.g. "S_TPINEL.xof")
//   Directory
```

**FileRecord** (embedded game files, only in `SPRITES.PBX`):
`u32 name_len` (no NUL), `char name[name_len]` (`GENBATT.bop`), `u32 size`, `u8 data[size]`.
Files come in sets `NAME.bop`, `NAME.fol`, `NAME.pal` (`.pal` is optional, e.g. `U_WATER`).
All 1461 embedded files (504 `.bop`, 504 `.fol`, 453 `.pal`, 349 unique names) are
**byte-identical to the files in `UPDATE/BINARY`**. `SPRITES.PBX` is a per-battle bundle of
the `.FOL/.BOP/.PAL` sprites described above, and needs no separate decoder.

**TextureRecord** (textures, "gif" is only the name of the source file): a serialized
Direct3D Retained Mode (Reality Lab) `D3DRMIMAGE`.

```c
uint32_t name_len;            // including the NUL
char     name[name_len];      // "s_gr4.gif\0"
uint32_t pixel_bytes;         // = width * height
uint32_t palette_bytes;       // always 1024
int32_t  width, height;       // 32 or 64 (also 32x64, 64x32)
int32_t  aspectx, aspecty;    // 1, 1       (missing in v1)
int32_t  depth;               // 8
int32_t  rgb;                 // 0 = palettized
int32_t  bytes_per_line;      // = width
uint8_t  buffer1_present;     // '1' (0x31)
uint8_t  pixels[pixel_bytes]; // 8-bit indices, rows top to bottom
uint8_t  buffer2_present;     // '0' (0x30), no second buffer
uint32_t red_mask, green_mask, blue_mask, alpha_mask;   // 0xFF, 0xFF, 0xFF, 0
uint32_t palette_size;        // used entries: 96, 97 or 256
struct { uint8_t r, g, b, flags; } palette[256];         // palette_bytes
uint32_t trailer_count;       // = palette_size (96/97/256)                      (hypothesis)
uint32_t trailer_depth;       // 8 (with 96/97) or 1 (with 256)                   (meaning unknown)
uint32_t transparent;         // 0/1; missing in v1                              (hypothesis)
uint32_t color;               // 0xFFRRGGBB, a representative colour of the texture
```

- `color` matches the dominant colour of the texture: water is blue, grass green, rocks grey.
  It is probably the colour used for flat or distant rendering. Hypothesis, not exact (it is not the average).
- `transparent = 1` on trees, flames, arrows, lightning and destroyed walls. Rendering with
  **black (RGB 0,0,0) as transparent** when the flag is set gives clean silhouettes. Index 0 is
  not the key colour: tree backgrounds use index 96. This is a hypothesis (D3DRM decal
  transparency), verified only visually.
- The palette is per texture (not `STANDARD.PAL`) and the colours are direct RGB.

**MeshBlob** (Reality Lab mesh, probably converted from DirectX `.x` files; the names end with `.xof`,
and `WHSHR.EXE` contains `%XoF`/`manyxof`):

```c
uint32_t nverts, nnormals;             // nnormals != nverts in 164 of 2404 meshes
float    verts[nverts][3];             // x, y, z; Y is up
float    normals[nnormals][3];
uint32_t nfaces, nrefs;                // nrefs = sum of per-face vertex counts
struct {                               // nfaces times
    uint32_t count, count2;            // always 3, 3 (triangles only)
    struct { uint32_t vertex, normal; } ref[count];
} faces[];
uint32_t face_texture[nfaces];         // index into this PBX's texture list (always < texture_count)
float    uv[nverts][2];                // per vertex, v = 0 at the top row of the image
```

**NameRecord**: `u32 name_len` (no NUL) + name.

**Directory** (end of file):

```c
uint32_t file_name_offs[file_count];   // offset of each FileRecord (its name_len field)
uint32_t file_size_offs[file_count];   // offset of its size field (= name_off + 4 + name_len)
uint32_t mesh_name_offs[mesh_count];   // offset of each NameRecord
uint32_t mesh_data_offs[mesh_count];   // offset of the matching MeshBlob
uint32_t dist[4];                      // distance from EOF to the start of each of the 4 arrays
```

Both arrays of names are **sorted case-insensitively** (like `stricmp`, which lowercases, so `_`
sorts before letters; 44/44 file lists and 44/44 mesh lists). The game probably looks names
up by binary search. Textures have no directory; meshes refer to them by index.

**Content of the three kinds:**

| File | Contents |
|---|---|
| `GRND.PBX` | 2–11 ground textures 64×64 (`gr1`, `mudgrass`, `crop1`, `u_water`, `cliffr`, `b_grock`, `uw_rock`; prefixes `s_` snow, `n_` night, `b_`/`uw_` probably badlands/underground; `null.gif` = blue/white clouds, a placeholder) + **one mesh `grnd.xof`**: the terrain surface (BF001: 468 vertices, 844 triangles) |
| `SCENERY.PBX` | 21–89 textures (tree billboards, house walls, rocks, flames, arrows, lightning) + 37–69 meshes: trees (`S_TPINEL` = snow triangular pine large, `TPINEL_D` = destroyed), rocks, buildings, bridges and **battle effect meshes** shared by all battles (`ARROWS1–3`, `SPEAR1–4`, `FIRE1–4`, `FLAMES1–4`, `LIGHT1–4`, `BOLTBUR1–4`, `EX1–8` = explosion frames, `SAPHARCH`) |
| `SPRITES.PBX` | `.bop/.fol/.pal` sets: `GENBATT` (generic battle effects, `loadspr:BattleSprites`) + sprites of the units and banners in this battle's `.BTS` |

**Scale:** the `grnd.xof` mesh of BF001 spans X 0..200, Z 0..220, and the `[FIELD]` is
1600×1760, so **1 mesh unit = 8 script units**, with X = script x and Z = script y. A top view
with Z pointing up matches the plan map `MAP001` (river at the top, gully at the bottom-right).
Heights in Y go from 0 to 34. Trees are about 11.5 units tall, which is about 92 script units.

#### Version 1 (only `MESH/BF004/GRND.PBX`, no `0x01` prefix)

Header after the magic has 5 u32 fields: `0, 256, texture_count, pixel_bytes, palette_bytes` (24 bytes).
Texture records have no `aspectx/aspecty` and have a 3-u32 trailer (no `transparent`).
Faces are `u32 count` + pairs (no `count2`). The mesh section has no directory, and meshes
are separated by extra float words. The first 3 meshes parse, then the layout differs.
The mesh section is extracted as raw bytes (`mesh_section_v1.bin`). The file is not used by the game scripts.

---

## How it was verified

| Check | Result |
|---|---|
| `.PBX` files | 133 (45 GRND, 44 SCENERY, 44 SPRITES) |
| Packed-data CRC from the header | 133/133 |
| Unpacked-data CRC after decompression | **133/133** |
| Structure: one RNC block exactly to EOF, no extra data | 133/133 |
| Container parsed with no leftover bytes (v2) | 132/132 |
| Texture pixel and palette totals equal the header | 133/133 |
| Embedded files (1461: 504 `.bop`, 504 `.fol`, 453 `.pal`) equal to `UPDATE/BINARY` | 1461/1461 |
| Sprite frames decoded with `render_sprites.decode_frame` (504 sets) | **28576/28576**, 0 errors |
| Textures parsed and written as PNG | 2003/2003 (229 GRND, 1774 SCENERY) |
| Meshes: parsed blob ends exactly at the next directory offset | **2404/2404** |
| Faces: all triangles, vertex/normal indices in range, `nrefs` correct, texture index < texture count | 112357 faces, 0 errors |
| Directory names sorted case-insensitively | 44/44 file lists, 44/44 mesh lists |
| `loadfurn` in `.BTS` → mesh name (table in `GAMEF.DLL`) → mesh present in that battle's `SCENERY.PBX` | 747 of 909 resolved and all 747 present; 162 not found by my crude table scan |
| PNG files written (texture sheets, per-texture PNG, mesh renders front/top, sprite sheets) | 2772, 0 errors |

Visual checks (rendered and viewed):
- `BF001/GRND`: snow textures, cliff, water. The terrain mesh from the top matches `MAP001`
  (river across the top, gully bottom-right, outline of the field).
- `BF001/SCENERY`: snow-covered pines as crossed billboard quads, darker destroyed pines, watch
  tower (stone base + wooden top), rocks, sapphire arch, flames, and an 8-frame explosion that
  breaks up from a fire ball into sparks.
- `BF015/SCENERY`: green pines, tent, rocks, stone pillars with carved runes, a slimy green monster
  texture. `BF034/SCENERY` textures: half-timbered house walls, windows, doors, wooden fences, and their
  destroyed variants.
- `BF020/GRND`: grass field with muddy patches and an irregular north edge. `BF036/GRND`: an L-shaped
  underground rock floor.
- Sprites: `CLANRATS` (skaven with blades, 8 directions), `GENBATT` (flames and burning
  figures), and banners.

## Relation to `.BTS` (notes only)

- `loadmesh:bf001` → `FILE/MESH/BF001/`. Names are not case-normalized (`Bf015`).
- `loadspr:BattleSprites` → `GENBATT.*`, `loadspr:u_water` → `U_WATER.*` (in `SPRITES.PBX`).
- `troopsprites`/`banner` of the units in the `.BTS` are in `SPRITES.PBX`. BF001: `ClanRats` →
  `CLANRATS`, `EshinAssassin` → `ESHIN`, `BorderHorse` → `BRDHRS`, `BorderSwordMen` → `BODYGRD`
  (probably), `BannerHiln` → `BANHILN`, `BannerSkaven3/5` → `BANSKAV3/5`.
  The player army from `.MRC` (`MercSword`, `MercXbow`, `BannerMrcCmdr`) is **not** in the PBX,
  so it is probably loaded from `BINARY/` directly.
- `loadfurn:SnwTriPineLrg` → mesh `S_TPINEL.xof`. `GAMEF.DLL` (and `WHSHR.EXE`) contain a table of
  60-byte records: the furniture name, and 16 bytes later the mesh name (`SnwTriPineLrg`/`S_TPINEL`,
  `D_SnwTriPineLrg`/`TPINEL_D`, `Explosion1`/`EX1`, `WatchTower`/`WATCHTOW`, `HumanTent`/`WIGWAM`…).
  The rest of the record is not examined. This is useful for ROADMAP 1.4 and 2.3.

## Scripts

```
python3 scripts/pbx_rnc.py ".../WARFB/FILE/MESH/BF001/SPRITES.PBX" sprites.bin   # unpack one file
python3 scripts/pbx_rnc.py --check ".../WARFB/FILE/MESH"                        # CRC check of all 133
python3 scripts/pbx_extract.py ".../WARFB" extracted/pbx [BF001 ...]            # full extraction (~50 s)
python3 scripts/pbx_extract.py --check ".../WARFB"                              # parse all, write nothing
```

- `scripts/pbx_rnc.py`: `crc16`, `parse_header`, `rnc_unpack(buf, pos)`, `unpack_pbx(path)`.
- `scripts/pbx_extract.py`: `parse_container(data)` returns files, textures, meshes and header.
  Also `render_mesh` (orthographic textured software rasterizer), `write_obj`, and `extract_pbx`.
  Output: `extracted/pbx/<BATTLE>/<GRND|SCENERY|SPRITES>/` with `index.json`, `files/`,
  `textures/NN_name.png`, `textures.png`, `materials.mtl`, `meshes/*.obj` (Wavefront OBJ with UV and
  normals), `meshes_front.png`, `meshes_top.png`, and `sprites/<NAME>.png` (first 16 frames).
  Sprites use `UPDATE/BINARY/STANDARD.PAL`; the battle's `loadpal` (night etc.) is ignored.

## Open questions
> **Tracked on GitHub**: these open items are tracked as issue #38 (`topic:sprites-animation`). Kept here for
> reference; a follow-up pass (issue #45) will verify nothing was lost in the move.


- The `0x01` byte before `RNC`, and header fields `unk8` (always 0) and `version = 207`.
- Texture trailer: `trailer_count`/`trailer_depth` pairs (96/8, 97/8, 256/1), the exact meaning of
  `transparent` and `color`, and why the texture `palette.flags` byte is sometimes non-zero.
- Mesh details: why `nnormals != nverts` in 164 meshes; whether `face_texture` ever selects a
  material rather than a texture; pivot and scale of scenery meshes versus `placefurniture` coordinates
  and `dir` (0..511).
- How `GRND.GD` (8192 × 24 B) relates to the `grnd.xof` mesh (another agent is working on GD).
- The full v1 mesh layout (`BF004/GRND.PBX`). It has low priority because no script uses the file.
- Full parse of the furniture table in `GAMEF.DLL` (162 `loadfurn` names were not found by the crude scan:
  `10mBlockWall`, `Stalagmite1`, `TorchFlame1`…).
- RNC method 1 is not implemented, because no game file uses it.

## Proposed changes to `ROADMAP.md`

- Terrain table: row "Terrain and 3D battle assets": `.PBX` ✅ (RNC + container fully decoded:
  textures, meshes, sprite bundles). `GRND.GD` stays 🟡.
- 2.1 → ✅. Note that `SPRITES.PBX` only bundles existing `BINARY` sprites (nothing new to decode),
  and that the "gif" files are Reality Lab `D3DRMIMAGE` textures, not GIF.
- 2.3 can start now: the terrain mesh (`grnd.xof`, scale 1:8 to script coordinates, Y up) and all
  scenery meshes are available as OBJ + PNG. A viewer needs `placefurniture` → mesh (table in
  `GAMEF.DLL`, see above) and the meaning of `dir`.
- 1.4 (names → sprite files): add the `GAMEF.DLL` furniture table and the per-battle `SPRITES.PBX`
  list as sources for mapping `troopsprites`/`banner` to 8.3 names.
- New small item: "Furniture table in `GAMEF.DLL` (60-byte records: name, mesh name, …)", size S.
