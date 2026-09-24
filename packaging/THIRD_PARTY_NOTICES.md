# Third-party notices

The Windows and Linux installers built from `packaging/` bundle this project's own code
(GPLv3, see `LICENSE`) together with a Python interpreter and the runtime frontend
dependencies from `requirements-engine.txt` (pygame-ce, zengl), so that end users don't need
to install Python themselves. This file records the license audit for that bundling
(GitHub issue #99) and the notices required by the bundled packages.

Only this project's own code and its Python dependencies are bundled. The original game's
files and assets are never included — see `CLAUDE.md`'s "Important rules for working on
this project".

## Audit conclusion

- **pygame-ce** ([pygame-ce.readthedocs.io](https://pyga.me/), PyPI `pygame-ce`) is licensed
  under the **GNU Lesser General Public License v2.1** (confirmed from the installed
  package's own `METADATA`). PyInstaller bundles pygame-ce's compiled extension modules and
  the native libraries it ships (listed below) as separate files next to the frozen
  executable, loaded by the OS's normal dynamic-linking mechanism (`LoadLibrary`/import) —
  not statically merged into a single binary blob with this project's own code. This is
  exactly the "suitable shared library mechanism" / dynamic-linking case LGPL 2.1 §6(b)
  describes, so the installer may bundle pygame-ce and be distributed under this project's
  own license (GPLv3, which is compatible with using an LGPL 2.1 library this way), provided
  the notices below accompany it. The full LGPL 2.1 text is included at
  `packaging/licenses/LGPL-2.1.txt` and reproduced with every install (see `installer.iss`'s
  `[Files]` section).
- **zengl** (PyPI `zengl`) is licensed under the **MIT License** (confirmed from the
  installed package's `dist-info/licenses/LICENSE`) — permissive, no redistribution
  obligations beyond keeping the notice. Full text below. zengl itself has no bundled
  third-party binaries; at runtime it only talks to the OS's own OpenGL driver, which is
  never redistributed.
- The native libraries pygame-ce's Windows wheel bundles (found under `pygame/*.dll` in the
  installed package; PyInstaller collects them via its own `hook-pygame.py`) are all under
  permissive licenses (zlib, BSD, MIT, or the IJG license) except FreeType, which pygame-ce's
  upstream build deliberately uses under its permissive **FreeType License (FTL)** rather
  than FreeType's alternative GPLv2 option (SDL_ttf's own prebuilt binaries, which pygame-ce
  reuses, are built this way specifically to keep SDL_ttf's own zlib license unencumbered).
  None of them impose obligations beyond attribution. See the per-library table below.

## Bundled native libraries (via pygame-ce's Windows wheel)

| File | Library | License | Homepage |
|---|---|---|---|
| `SDL2.dll` | SDL2 | zlib License | https://www.libsdl.org/ |
| `SDL2_image.dll`, `libjpeg-62.dll`, `libpng16-16.dll`, `libtiff-5.dll`, `libwebp-7.dll`, `libwebpdemux-2.dll` | SDL2_image and its codecs (libjpeg-turbo, libpng, libtiff, libwebp) | zlib / IJG / libpng / libtiff / BSD-3-Clause (all permissive) | https://github.com/libsdl-org/SDL_image |
| `SDL2_mixer.dll`, `libogg-0.dll`, `libopus-0.dll`, `libopusfile-0.dll`, `libwavpack-1.dll`, `libxmp.dll` | SDL2_mixer and its codecs (libogg, libopus, libopusfile, WavPack, libxmp) | zlib / BSD-3-Clause / BSD-2-Clause / MIT (all permissive) | https://github.com/libsdl-org/SDL_mixer |
| `SDL2_ttf.dll`, `freetype.dll` | SDL2_ttf, FreeType | zlib, FreeType License (FTL) | https://github.com/libsdl-org/SDL_ttf, https://freetype.org/ |
| `portmidi.dll` | PortMidi | MIT-style PortMidi license | https://sourceforge.net/projects/portmedia/ |

Full texts for the two libraries this project depends on directly are below; the native
libraries above are all short, standard permissive licenses (zlib/BSD/MIT/IJG) — their
canonical texts are available at the homepages listed. This table itself is the required
attribution notice for them.

## pygame-ce (LGPL 2.1)

Copyright (c) the pygame-ce contributors. Source: https://github.com/pygame-community/pygame-ce

Full license text: `packaging/licenses/LGPL-2.1.txt` (also reproduced at
https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html).

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
