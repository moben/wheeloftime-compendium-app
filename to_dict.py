#!/usr/bin/env python3

from dataclasses import dataclass
from textwrap import dedent
import json
import re
from pyglossary.glossary_v2 import Glossary

# Glossary.init() should be called only once, so make sure you put it
# in the right place
Glossary.init()


@dataclass
class dict_entry:
    definitions: list[tuple[str, str]]
    backlinks: list[tuple[str, set[str]]]


class wot_dict:
    _entries: dict[str, dict_entry]
    _link_patterns: dict[re.Pattern, str]

    def __init__(self) -> None:
        self._entries = {}
        self._link_patterns = {}

    @staticmethod
    def _compile_link_patterns(jdata):
        # This seems backwards, but there's at least one name that's in two book json
        # files but with a different id.
        # In any case, what we really need is to find the name for a given id link.
        return {re.compile(rf"\[([^]]*)\]\(#{jd['id']}\)"): jd["name"] for jd in jdata}

    def _find_backlinks(self, name: str, jdata) -> list[str]:
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
                rf"""<a class="dict-internal-link" href="bword://{name}">\1</a>""", defi
            )
        # markdown emphasis
        defi = re.sub(r"_([^ ]+)_", r"""<em class="dict-emphasis">\1</em>""", defi)
        return defi

    def ingest(self, input_file: str, booktitle: str) -> None:
        with open(input_file) as jf:
            jdata = json.load(jf)

        self._link_patterns |= self._compile_link_patterns(jdata)

        for d in jdata:
            backlinks = self._find_backlinks(d["name"], jdata)
            if d["name"] in self._entries:
                e = self._entries[d["name"]]
                self._entries[d["name"]] = dict_entry(
                    definitions=[
                        (
                            f"{booktitle}, {d["chapter"]}",
                            self._convert_defi_links(d["info"]),
                        ),
                        *e.definitions,
                    ],
                    backlinks=[
                        (
                            booktitle,
                            backlinks,
                        ),
                        *((book, links - backlinks) for (book, links) in e.backlinks),
                    ],
                )
            else:
                self._entries[d["name"]] = dict_entry(
                    definitions=[
                        (
                            f"{booktitle}, {d["chapter"]}",
                            self._convert_defi_links(d["info"]),
                        ),
                    ],
                    backlinks=[
                        (
                            booktitle,
                            backlinks,
                        ),
                    ],
                )

    @staticmethod
    def _get_alt_words(word):
        def _get_words():
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

    def write_dict(self, output_basename: str, dicttitle: str):
        glos = Glossary()

        for en, e in self._entries.items():
            defs = "\n".join(
                dedent(
                    f"""\
                    <div class="dict-origin">{chap}</div>
                    <div class="dict-definition">{defi}</div>
                    <hr>
                    """,
                )
                for (chap, defi) in e.definitions
            )
            backlinks = "\n".join(
                dedent(
                    f"""\
                    <dl class="dict-backlinks">
                    <dt>Backlinks{f''' ({book})''' if len(e.backlinks) > 1 else ''}:</dt>
                    {"\n".join(f'''<dd><a href="bword://{l}">{l}</a></dd>''' for l in sorted(links))}
                    </dl>
                    """,
                )
                for book, links in e.backlinks
            )
            glos.addEntry(
                glos.newEntry(
                    [en, *self._get_alt_words(en)],
                    dedent(
                        f"""\
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
                )
            )

        glos.setInfo("title", dicttitle)
        glos.setInfo("author", "Karl Hammond, Jason Wright")
        glos.write(
            f"{output_basename}.ifo",
            format="Stardict",
            # koreader is fine with compressed .dict, but won't read compressed .syn
            dictzip=False,
        )
        with open(f"{output_basename}.css", "w") as f:
            f.write(
                dedent(
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
            )


def main():
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
        "00": "New Spring",
        "11": "Knife of Dreams",
        "12": "The Gathering Storm",
        "13": "Towers of Midnight",
        "14": "A Memory of Light",
    }
    wot_cumulative_dicts = wot_dict()

    for num, name in books.items():
        print(f"Converting {num} {name}")
        wot_cumulative_dicts.ingest(
            f"assets/data/book-{num}.json",
            name,
        )
        wot_cumulative_dicts.write_dict(
            f"wot-cumulative-book-{num}",
            f"Wheel of Time Compendium {num}: {name}",
        )
        wot_single_dict = wot_dict()
        wot_single_dict.ingest(
            f"assets/data/book-{num}.json",
            name,
        )
        wot_single_dict.write_dict(
            f"wot-book-{num}",
            f"Wheel of Time Compendium {num}: {name}",
        )


if __name__ == "__main__":
    main()
