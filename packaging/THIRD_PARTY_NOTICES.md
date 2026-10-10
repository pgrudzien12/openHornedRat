# Third-party notices

Every package built from `packaging/` -- the Windows installer, the Linux AppImage, `.deb` and `.rpm`, and the
macOS package -- bundles this project's own code (GPLv3, see `LICENSE`) together with a Python interpreter, the
Tcl/Tk libraries the launcher window needs, and the runtime frontend dependencies from `requirements-engine.txt`
(pygame-ce, zengl), so that end users don't need to install Python themselves. This file records the license audit
for that bundling (GitHub issues #99 and #107) and the notices required by the bundled packages.

Only this project's own code and its Python dependencies are bundled. The original game's
files and assets are never included -- see `CLAUDE.md`'s "Important rules for working on
this project".

## Audit conclusion

- **pygame-ce** ([pygame-ce.readthedocs.io](https://pyga.me/), PyPI `pygame-ce`) is licensed
  under the **GNU Lesser General Public License v2.1** (confirmed from the installed
  package's own `METADATA`). PyInstaller bundles pygame-ce's compiled extension modules and
  the native libraries it ships (listed below) as separate files next to the frozen
  executable, loaded by the OS's normal dynamic-linking mechanism -- not statically merged
  into a single binary blob with this project's own code. This is exactly the "suitable
  shared library mechanism" / dynamic-linking case LGPL 2.1 §6(b) describes, so the
  packages may bundle pygame-ce and be distributed under this project's own license (GPLv3,
  which is compatible with using an LGPL 2.1 library this way), provided the notices below
  accompany them. A user can replace any of these libraries by dropping a modified build
  next to the executable (the Windows, `.deb`, `.rpm` and macOS installs are plain
  directories; the AppImage can be unpacked with `--appimage-extract`). The full LGPL 2.1
  text is included at `packaging/licenses/LGPL-2.1.txt` and installed with every package.
- **zengl** (PyPI `zengl`) is licensed under the **MIT License** (confirmed from the
  installed package's `dist-info/licenses/LICENSE`) -- permissive, no redistribution
  obligations beyond keeping the notice. Full text below. zengl itself has no bundled
  third-party binaries; at runtime it only talks to the OS's own OpenGL driver, which is
  never redistributed.
- **The native libraries inside pygame-ce's wheels differ per platform** (tables below). They
  were checked against the license files pygame-ce 2.5.8 ships in its own source
  distribution (`docs/licenses/`). Everything is permissive (zlib, BSD, MIT, IJG, libpng,
  libtiff, Apache-2.0) except:
  - **FluidSynth** and **mpg123**, both **LGPL 2.1**, on Linux and macOS -- covered by the
    same §6(b) dynamic-linking argument as pygame-ce itself;
  - **libsndfile** (Linux and macOS) and **ALSA** `libasound` (Linux only), which are
    LGPL-2.1-or-later upstream. Their release license texts and copyright notices are
    included below;
  - **FreeType**, which pygame-ce's build uses under its permissive **FreeType License
    (FTL)** rather than the alternative GPLv2 option.
- **PortMidi** is licensed under the **Apache License 2.0** (pygame-ce's `LICENSE.portmidi.txt`).
  An earlier version of this file called it "MIT-style"; that was wrong. Apache-2.0 is
  compatible with GPLv3 and requires the license text to accompany the package, which is
  `packaging/licenses/Apache-2.0.txt`.
- **CPython**, the **Tcl/Tk** libraries and **PyInstaller** are covered in their own section
  below.

## Bundled native libraries -- Windows wheel

| File | Library | License | Homepage |
|---|---|---|---|
| `SDL2.dll` | SDL2 | zlib License | https://www.libsdl.org/ |
| `SDL2_image.dll`, `libjpeg-62.dll`, `libpng16-16.dll`, `libtiff-5.dll`, `libwebp-7.dll`, `libwebpdemux-2.dll` | SDL2_image and its codecs (libjpeg-turbo, libpng, libtiff, libwebp) | zlib / IJG / libpng / libtiff / BSD-3-Clause (all permissive) | https://github.com/libsdl-org/SDL_image |
| `SDL2_mixer.dll`, `libogg-0.dll`, `libopus-0.dll`, `libopusfile-0.dll`, `libwavpack-1.dll`, `libxmp.dll` | SDL2_mixer and its codecs (libogg, libopus, libopusfile, WavPack, libxmp) | zlib / BSD-3-Clause / BSD-2-Clause / MIT (all permissive) | https://github.com/libsdl-org/SDL_mixer |
| `SDL2_ttf.dll`, `freetype.dll` | SDL2_ttf, FreeType | zlib, FreeType License (FTL) | https://github.com/libsdl-org/SDL_ttf, https://freetype.org/ |
| `portmidi.dll` | PortMidi | Apache License 2.0 | https://sourceforge.net/projects/portmedia/ |

## Bundled native libraries -- Linux and macOS wheels

Shared by both platforms (Linux ships them as `lib<name>-<hash>.so.*` in `pygame_ce.libs`, macOS as
`lib<name>.*.dylib` in `pygame/.dylibs`). Library names below are the file stems.

| Library | License | Notes |
|---|---|---|
| `libSDL2`, `libSDL2_image`, `libSDL2_mixer`, `libSDL2_ttf` | zlib License | |
| `libfreetype` | FreeType License (FTL) | used under FTL, not GPLv2 |
| `libharfbuzz` | MIT (HarfBuzz "old MIT") | text shaping for SDL2_ttf; not in pygame-ce's license directory |
| `libbrotlicommon`, `libbrotlidec` | MIT | used by FreeType for WOFF2 |
| `libpng16` | libpng license v2 | |
| `libjpeg` | IJG license | |
| `libtiff` | libtiff license (BSD-like) | |
| `libwebp`, `libwebpdemux`, `libsharpyuv` | BSD-3-Clause | |
| `libogg`, `libvorbis`, `libvorbisenc`, `libvorbisfile` | BSD-3-Clause | |
| `libopus`, `libopusfile` | BSD-3-Clause | |
| `libFLAC` | BSD-3-Clause | |
| `libwavpack` | BSD-3-Clause | |
| `libxmp` | MIT | |
| `libportmidi` | Apache License 2.0 | text in `packaging/licenses/Apache-2.0.txt` |
| `libfluidsynth` | **LGPL 2.1** | verified from pygame-ce's `LICENSE.fluidsynth.txt` |
| `libmpg123` | **LGPL 2.1** | verified from pygame-ce's `LICENSE.mpg123.txt` |
| `libsndfile` | **LGPL-2.1-or-later** | Release source grants version 2.1 or later; notice and full text below |
| `libasound` (Linux only) | **LGPL-2.1-or-later** | Release source grants version 2.1 or later; notice and full text below |
| `libz` (macOS only, zlib-ng build) | zlib License | |

The license texts pygame-ce 2.5.8 ships for these libraries (`docs/licenses/` in its source
distribution) are included unchanged in `packaging/licenses/third-party/` and installed with every package:

| Text | Covers |
|---|---|
| `LICENSE.sdl2.txt`, `LICENSE.sdl2_image.txt`, `LICENSE.sdl2_mixer.txt` | SDL2, SDL2_image, SDL2_mixer |
| `LICENSE.zlib.txt` | zlib / zlib-ng |
| `LICENSE.freetype.txt` | FreeType (FTL) |
| `LICENSE.png.txt`, `LICENSE.jpeg.txt`, `LICENSE.tiff.txt`, `LICENSE.webp.txt` | libpng, libjpeg(-turbo), libtiff, libwebp (and libsharpyuv) |
| `LICENSE.ogg-vorbis.txt`, `LICENSE.opus.txt`, `LICENSE.opusfile.txt`, `LICENSE.FLAC.txt` | Ogg, Vorbis, Opus, opusfile, FLAC |
| `LICENSE.fluidsynth.txt`, `LICENSE.mpg123.txt` | FluidSynth, mpg123 (LGPL 2.1) |
| `LICENSE.sdl2_ttf.txt` | SDL2_ttf |
| `LICENSE.harfbuzz.txt` | HarfBuzz |
| `LICENSE.brotli.txt` | brotli |
| `LICENSE.wavpack.txt` | WavPack |
| `LICENSE.libxmp.txt` | libxmp |
| `LICENSE.libsndfile.txt`, `LICENSE.alsa.txt` | libsndfile and ALSA `libasound` (LGPL 2.1 text) |

PortMidi's text is `packaging/licenses/Apache-2.0.txt`. The additional texts above are from
these upstream releases (the release identifies the source of the notice text, not necessarily
the version of a native binary in a pygame-ce wheel):

| Text | Upstream release file |
|---|---|
| `LICENSE.sdl2_ttf.txt` | [SDL_ttf 2.24.0 `LICENSE.txt`](https://raw.githubusercontent.com/libsdl-org/SDL_ttf/release-2.24.0/LICENSE.txt) |
| `LICENSE.harfbuzz.txt` | [HarfBuzz 10.4.0 `COPYING`](https://raw.githubusercontent.com/harfbuzz/harfbuzz/10.4.0/COPYING) |
| `LICENSE.brotli.txt` | [brotli 1.1.0 `LICENSE`](https://raw.githubusercontent.com/google/brotli/v1.1.0/LICENSE) |
| `LICENSE.wavpack.txt` | [WavPack 5.8.1 `COPYING`](https://raw.githubusercontent.com/dbry/WavPack/5.8.1/COPYING) |
| `LICENSE.libxmp.txt` | [libxmp 4.6.3 `docs/COPYING`](https://raw.githubusercontent.com/libxmp/libxmp/libxmp-4.6.3/docs/COPYING) |
| `LICENSE.libsndfile.txt` | [libsndfile 1.2.2 `COPYING`](https://raw.githubusercontent.com/libsndfile/libsndfile/1.2.2/COPYING) |
| `LICENSE.alsa.txt` | [alsa-lib 1.2.13 `COPYING`](https://raw.githubusercontent.com/alsa-project/alsa-lib/v1.2.13/COPYING) |

The libsndfile 1.2.2 source header credits Erik de Castro Lopo (1999–2018) and permits
LGPL version 2.1 or any later version. The alsa-lib 1.2.13 PCM source header credits Jaroslav
Kysela (1998) and Abramo Bagnara (2000) and grants the same version choice. Their `COPYING`
files supply the complete LGPL 2.1 text; this is why both libraries remain classified as
LGPL-2.1-or-later rather than LGPL-2.1-only.

## Python, Tcl/Tk and PyInstaller

- **CPython** (interpreter, standard library) is licensed under the **PSF License
  Agreement** (https://docs.python.org/3/license.html), a permissive license compatible with
  GPLv3. Its complete license and copyright notices are in
  `packaging/licenses/third-party/LICENSE.python.txt`
  ([CPython 3.12.12 `LICENSE`](https://raw.githubusercontent.com/python/cpython/v3.12.12/LICENSE)).
- **Tcl/Tk** (`_tkinter`'s libraries, used by the launcher window) is under the **Tcl/Tk
  License**, a BSD-style permissive license (https://www.tcl-lang.org/software/tcltk/license.html).
  Linux's uv Python bundle uses Tcl/Tk 9.0; `LICENSE.tcl-9.0.txt` and `LICENSE.tk-9.0.txt`
  contain their separate notices from [Tcl 9.0.2](https://raw.githubusercontent.com/tcltk/tcl/core-9-0-2/license.terms)
  and [Tk 9.0.2](https://raw.githubusercontent.com/tcltk/tk/core-9-0-2/license.terms). Windows and
  macOS use Tcl/Tk 8.6; `LICENSE.tcl-8.6.txt` and `LICENSE.tk-8.6.txt` contain the corresponding
  notices from [Tcl 8.6.15](https://raw.githubusercontent.com/tcltk/tcl/core-8-6-15/license.terms)
  and [Tk 8.6.15](https://raw.githubusercontent.com/tcltk/tk/core-8-6-15/license.terms). The Tcl
  and Tk texts retain their distinct copyright notices.
- **PyInstaller** (the freezing tool) is GPL-2.0-or-later with an exception that explicitly
  allows the executables it produces, including its bootloader, to be distributed under any
  license, so it places no obligation on the packages.

The license files are installed with every package alongside this notice: Windows via
`installer.iss`, and Linux/macOS via their respective package recipes. When
`requirements-engine.txt` changes, re-run `tests/test_packaging_notices.py` and update the
tables above.

## pygame-ce (LGPL 2.1)

Copyright (c) the pygame-ce contributors. Source: https://github.com/pygame-community/pygame-ce
(version 2.5.8 is the one `requirements-engine.txt` pins; its source distribution is on PyPI
as `pygame-ce` 2.5.8).

Full license text: `packaging/licenses/LGPL-2.1.txt` (also reproduced at
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

## PortMidi (Apache-2.0)

Full license text: `packaging/licenses/Apache-2.0.txt`.

## zengl (MIT)

```
MIT License

Copyright (c) 2024 Szabolcs Dombi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
