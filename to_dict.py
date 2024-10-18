#!/usr/bin/env python3
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from functools import reduce
from pathlib import Path
from textwrap import dedent
from typing import Iterator, TypedDict

from pyglossary.glossary_v2 import Glossary

# Glossary.init() should be called only once, so make sure you put it
# in the right place
Glossary.init()


class BookData(TypedDict):
    id: str
    name: str
    chapter: str
    info: str


@dataclass(frozen=True, kw_only=True, slots=True)
class DictEntry:
    book_number: int
    book_title: str
    chapter: str
    definition: str
    backlinks: set[str]


class WoTDict:
    _entries: dict[str, list[DictEntry]]
    _link_patterns: dict[re.Pattern[str], str]

    def __init__(self) -> None:
        self._entries = {}
        self._link_patterns = {}

    @staticmethod
    def _compile_link_patterns(jdata: list[BookData]) -> dict[re.Pattern[str], str]:
        # This seems backwards, but there's at least one name that's in two book json
        # files but with a different id.
        # In any case, what we really need is to find the name for a given id link.
        return {re.compile(rf"\[([^]]*)\]\(#{jd['id']}\)"): jd["name"] for jd in jdata}

    def _find_backlinks(self, name: str, jdata: list[BookData]) -> set[str]:
        backlink_patterns = [r for r, n in self._link_patterns.items() if n == name]
        return {
            jd["name"]
            for jd in jdata
            if any(p.search(jd["info"]) for p in backlink_patterns)
        }

    def _convert_defi_links(self, defi: str) -> str:
        for r, name in self._link_patterns.items():
            # At least sdcv / koreader need the link target verbatim (not html escaped or url escaped)
            # https://github.com/ilius/pyglossary/issues/456
            defi = r.sub(
                rf"""<a class="dict-internal-link" href="bword://{name}">\1</a>""",
                defi,
            )
        # markdown emphasis
        return re.sub(r"_([^ ]+)_", r"""<em class="dict-emphasis">\1</em>""", defi)

    def ingest(self, input_file: str, booknumber: int, booktitle: str) -> None:
        with Path(input_file).open() as jf:
            jdata: list[BookData] = json.load(jf)

        self._link_patterns |= self._compile_link_patterns(jdata)

        for d in jdata:
            new_entry = DictEntry(
                book_number=booknumber,
                book_title=booktitle,
                chapter=d["chapter"],
                definition=self._convert_defi_links(d["info"]),
                backlinks=self._find_backlinks(d["name"], jdata),
            )
            if d["name"] in self._entries:
                _ets = sorted(
                    (new_entry, *self._entries[d["name"]]),
                    key=lambda e: e.book_number,
                    reverse=True,
                )
                self._entries[d["name"]] = [
                    DictEntry(
                        book_number=e.book_number,
                        book_title=e.book_title,
                        chapter=e.chapter,
                        definition=e.definition,
                        backlinks=reduce(
                            lambda x, y: x - y,
                            (
                                ee.backlinks
                                for ee in _ets
                                if ee.book_number > e.book_number
                            ),
                            e.backlinks,
                        ),
                    )
                    for e in _ets
                ]
            else:
                self._entries[d["name"]] = [new_entry]

    @staticmethod
    def _get_alt_words(word: str) -> Iterator[str]:
        def _get_words() -> Iterator[str]:
            # word itself needs to be in synonyms, at least for sdcv
            yield word

            if wparens := re.match(r"([^(]*[^( ]) *\(([^)]*)\) *(.*)", word):
                if wparens.group(3):
                    # Robert (Bob) Jordan -> Bob Jordan
                    yield f"{wparens.group(2)} {wparens.group(3)}"
                else:
                    # Robert (of Jordan) -> Robert of Jordan
                    yield f"{wparens.group(1)} {wparens.group(2)}"
                # Robert (Bob) Jordan -> Robert Jordan
                yield f"{wparens.group(1)} {wparens.group(3)}"

            for w in word.split(" "):
                # Paranoia check for empty parens
                if ww := w.strip("()"):
                    #     and ww.lower() != ww:
                    # Exclude words like: of, al, ...
                    # as well as normal words within names
                    # Might make sense to replace this with an explicit filter if it
                    # ever becomes useful to look up people who have an "al" or "din" in
                    # their name?
                    # On the other hand, it doesn't really hurt to have "of" in the
                    # dictionary, that doesn't get in the way unless one tries to look
                    # it up...

                    yield ww
                    # al'Jordan -> Jordan
                    if wprefixed := re.match(r"[a-z]{1,2}'(.*)", ww):
                        # As above, maybe also yield the prefix?
                        yield wprefixed.group(1)

        for w in _get_words():
            yield w
            # Needed at least in koreader for lower-case lookups that otherwise
            # exactly match the full name
            yield w.lower()

    def write_dict(self, output_basename: str, dicttitle: str) -> None:
        glos = Glossary()

        style = dedent(
            """\
            .dict-origin {
                font-size: smaller;
                font-style: italic;
                padding-bottom: 1em;
            }

            .dict-definition {}

            .dict-backlinks {
                font-size: smaller;
            }

            .dict-backlinks > dt {
                font-weight: bold;
            }

            .dict-backlinks > dd {
                font-style: italic;
            }

            .dict-internal-link {}

            .dict-emphasis {}
            """,
        )
        for en, ets in self._entries.items():
            defs = "\n<hr>\n".join(
                dedent(
                    f"""\
                    <div class="dict-origin">{e.book_title}, {e.chapter}</div>
                    <div class="dict-definition">{e.definition}</div>
                    """,
                )
                for e in ets
            )

            backlinks = (
                "\n".join(
                    dedent(
                        f"""\
                        <hr>
                        <dl class="dict-backlinks">
                        <dt>Backlinks{f''' ({e.book_title})''' if len(ets) > 1 else ''}:</dt>
                        {"\n".join(f'''<dd><a href="bword://{link}">{link}</a></dd>''' for link in sorted(e.backlinks))}
                        </dl>
                        """,
                    )
                    for e in ets
                )
                if any(e.backlinks for e in ets)
                else ""
            )
            glos.addEntry(
                glos.newEntry(
                    [en, *self._get_alt_words(en)],
                    dedent(
                        f"""\
                        <style>
                        {style}
                        </style>
                        <link rel="stylesheet" type="text/css" href="{output_basename}.css"/>
                        <div>
                        {defs}
                        <div>
                        {backlinks}
                        </div>
                        </div>
                        """,
                    ),
                    defiFormat="h",  # "m" for plain text, "h" for HTML
                ),
            )

        glos.setInfo("title", dicttitle)
        glos.setInfo("author", "Karl Hammond, Jason Wright")
        glos.write(
            f"{output_basename}.ifo",
            format="Stardict",
        )

        # koreader is fine with compressed .dict, but won't read compressed .syn
        with gzip.open(f"{output_basename}.syn.dz", mode="rb") as syndz:
            Path(f"{output_basename}.syn").write_bytes(syndz.read())
        Path(f"{output_basename}.syn.dz").unlink()

        with Path(f"{output_basename}.css").open("w") as f:
            f.write(style)


def build_dict(var, num: str, name: str) -> None:
    Path(f"dicts/{var['prefix']}").mkdir(parents=True, exist_ok=True)

    dict_obj = var.get("dict", WoTDict())
    dict_obj.ingest(
        f"assets/data/book-{num}.json",
        int(num),
        name,
    )
    dict_obj.write_dict(
        f"dicts/{var['prefix']}/{var['prefix']}-book-{num}",
        var["title_fmt"].format(num=num, name=name),
    )


def main() -> None:
    books = {
        "01": "The Eye of the World",
        "02": "The Great Hunt",
        "03": "The Dragon Reborn",
        "04": "The Shadow Rising",
        "05": "The Fires of Heaven",
        "06": "Lord of Chaos",
        "07": "A Crown of Swords",
        "08": "The Path of Daggers",
        "09": "Winter's Heart",
        "10": "Crossroads of Twilight",
        "11": "Knife of Dreams",
        "12": "The Gathering Storm",
        "13": "Towers of Midnight",
        "14": "A Memory of Light",
    }
    new_spring = ("00", "New Spring")
    variants = {
        "independent": {
            "after": None,
            "prefix": "wot",
            "title_fmt": "WoT Compendium {num}: {name}",
        },
        "ns_chronological": {
            "after": None,
            "dict": WoTDict(),
            "prefix": "wot-cumulative-ns_chronological",
            "title_fmt": "WoT Compendium (cumulative, NS chronological) {num}: {name}",
        },
        "ns_publishing": {
            "after": "10",
            "dict": WoTDict(),
            "prefix": "wot-cumulative-ns_publishing",
            "title_fmt": "WoT Compendium (cumulative, NS publishing) {num}: {name}",
        },
        "ns_last": {
            "after": "14",
            "dict": WoTDict(),
            "prefix": "wot-cumulative-ns_last",
            "title_fmt": "WoT Compendium (cumulative, NS last) {num}: {name}",
        },
    }

    def cond_build_new_spring(current_num: None | str):
        for var in variants.values():
            if var["after"] == current_num:
                build_dict(var, *new_spring)

    print(f"Converting {' '.join(new_spring)}")
    cond_build_new_spring(None)
    for num, name in books.items():
        print(f"Converting {num} {name}")
        for var in variants.values():
            build_dict(var, num, name)
        cond_build_new_spring(num)


if __name__ == "__main__":
    main()
