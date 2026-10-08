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
    LGPL-2.1-or-later upstream. pygame-ce's source distribution carries no license text for
    these two, so this rests on the upstream projects' published licenses and is listed
    under "Open items" for re-checking against their release tarballs;
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
| `libsndfile` | **LGPL-2.1-or-later** (upstream) | not verified against a shipped license text; see Open items |
| `libasound` (Linux only) | **LGPL-2.1-or-later** (upstream ALSA) | not verified against a shipped license text; see Open items |
| `libz` (macOS only, zlib-ng build) | zlib License | |

Short permissive licenses (zlib, BSD, MIT, IJG) require only that their copyright notice and
disclaimer accompany binary redistributions; this table is the attribution notice for them,
and the canonical texts are in pygame-ce's source distribution (`docs/licenses/`, PyPI
`pygame-ce` 2.5.8 sdist) and at each project's homepage.

## Python, Tcl/Tk and PyInstaller

- **CPython** (interpreter, standard library) is licensed under the **PSF License
  Agreement** (https://docs.python.org/3/license.html), a permissive license compatible with
  GPLv3. It is bundled in every package.
- **Tcl/Tk** (`_tkinter`'s libraries, used by the launcher window) is under the **Tcl/Tk
  License**, a BSD-style permissive license (https://www.tcl-lang.org/software/tcltk/license.html).
- **PyInstaller** (the freezing tool) is GPL-2.0-or-later with an exception that explicitly
  allows the executables it produces, including its bootloader, to be distributed under any
  license, so it places no obligation on the packages.

## Open items

These are known gaps in the audit, not blockers found so far:

1. Re-check **libsndfile** and **ALSA** `libasound` against their upstream release tarballs
   (pygame-ce ships no license text for them) before the first public release.
2. The PSF license and the Tcl/Tk license each require their copyright notice and license
   text to accompany binary redistributions. They are only referenced by link here; the texts
   should be shipped with the packages (taken from the exact interpreter the build uses).
3. When `requirements-engine.txt` changes, re-run the check in `tests/test_packaging_notices.py`
   and update the tables above.

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
