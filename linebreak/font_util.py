#!/usr/bin/env python3
"""Font discovery helpers, backed by fontconfig's fc-list."""

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class FontInfo:
    family: str   # may be comma-separated localized names, e.g. 'WenYuan Sans SC,文渊黑体'
    style: str    # e.g. 'Regular', 'Bold'; may also be comma-separated
    path: str     # file path for the font file
    index: int    # face index within a .ttc collection, 0 for single-face files


def list_fonts(lang: str = '') -> list[FontInfo]:
    """Lists installed fonts, optionally only those covering `lang` (e.g. 'zh', 'ja')."""
    pattern = f':lang={lang}' if lang else ':'
    out = subprocess.run(
        ['fc-list', pattern, '--format', '%{family}\t%{style}\t%{file}\t%{index}\n'],
        capture_output=True, text=True, check=True).stdout
    fonts = set()
    for line in out.splitlines():
        family, style, path, index = line.split('\t')
        # Named instances of variable fonts have the instance number in the
        # high 16 bits; the low 16 bits are the face index.
        fonts.add(FontInfo(family, style, path, int(index) & 0xFFFF))
    return sorted(fonts)


def list_cjk_fonts(lang: str = 'zh') -> list[FontInfo]:
    """Lists installed CJK fonts. `lang` can be 'zh', 'zh-cn', 'zh-tw', 'ja', 'ko', etc."""
    return list_fonts(lang)


GENERIC_FAMILIES = {'serif', 'sans', 'sans-serif', 'monospace', 'mono', 'cursive', 'fantasy'}


def find_font(pattern: str, strict: bool = True) -> FontInfo | None:
    """Finds the best installed font for a fontconfig pattern.

    `pattern` is a family name, optionally followed by properties, e.g.
    'Noto Serif CJK SC', 'Noto Serif CJK SC:bold', '文渊宋体', 'serif:lang=zh-cn'.

    fc-match always returns some font, so when `strict` is true, returns None
    unless the matched font really has the requested family name.  Generic
    families ('serif', 'sans-serif', ...) are resolved by fontconfig and are
    never rejected.
    """
    out = subprocess.run(
        ['fc-match', '--format', '%{family}\t%{style}\t%{file}\t%{index}\n', pattern],
        capture_output=True, text=True, check=True).stdout
    if not out.strip():
        return None
    family, style, path, index = out.splitlines()[0].split('\t')
    font = FontInfo(family, style, path, int(index) & 0xFFFF)

    wanted = pattern.split(':')[0].strip().lower()
    if strict and wanted and wanted not in GENERIC_FAMILIES:
        if wanted not in [name.strip().lower() for name in family.split(',')]:
            return None
    return font


# Preferred fonts for typesetting body text, most preferred first.  Serif
# (Song/Ming) faces are the convention for running text in CJK.
DEFAULT_CJK_FONTS = {
    'zh-cn': ['Noto Serif CJK SC', 'Source Han Serif SC', 'Source Han Serif CN',
              'WenYuan Serif SC', 'Songti SC', 'SimSun',
              'Noto Sans CJK SC', 'Source Han Sans SC'],
    'zh-tw': ['Noto Serif CJK TC', 'Source Han Serif TC', 'Source Han Serif TW',
              'Songti TC', 'PMingLiU',
              'Noto Sans CJK TC', 'Source Han Sans TC'],
    'zh-hk': ['Noto Serif CJK HK', 'Source Han Serif HC', 'Source Han Serif HK',
              'Noto Serif CJK TC', 'Noto Sans CJK HK'],
    'ja': ['Noto Serif CJK JP', 'Source Han Serif', 'Source Han Serif JP',
           'Hiragino Mincho ProN', 'Yu Mincho', 'IPAexMincho',
           'Noto Sans CJK JP', 'Source Han Sans'],
    'ko': ['Noto Serif CJK KR', 'Source Han Serif K', 'Source Han Serif KR',
           'AppleMyungjo', 'Batang',
           'Noto Sans CJK KR', 'Source Han Sans K'],
}
DEFAULT_CJK_FONTS['zh'] = DEFAULT_CJK_FONTS['zh-cn']


def default_cjk_font(lang: str = 'zh-cn') -> FontInfo | None:
    """Returns a good installed font for typesetting CJK text in `lang`.

    Tries well-known serif faces first, then whatever fontconfig picks as
    'serif' for the language, as long as it really covers the language.
    Returns None if there is no font for the language at all.
    """
    lang = lang.lower()
    for family in DEFAULT_CJK_FONTS.get(lang, []):
        font = find_font(family)
        if font:
            return font
    font = find_font(f'serif:lang={lang}')
    if font and font in list_fonts(lang):
        return font
    fonts = list_fonts(lang)
    return fonts[0] if fonts else None


def print_font_list(lang):
    for font in list_cjk_fonts(lang):
        print(f'{font.family} [{font.style}]  {font.path}#{font.index}')
    print('default:', default_cjk_font(lang))


if __name__ == '__main__':
    lang = sys.argv[1] if len(sys.argv) > 1 else 'zh-cn'
    print_font_list(lang)
