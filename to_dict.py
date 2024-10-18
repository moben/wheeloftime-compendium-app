#!/usr/bin/env python3

from textwrap import dedent
import json
import re
from pyglossary.glossary_v2 import Glossary

# Glossary.init() should be called only once, so make sure you put it
# in the right place
Glossary.init()


def write_dict(input_file: str, output_basename: str, booknumber: str, booktitle: str):
    with open(input_file) as jf:
        jdata = json.load(jf)

    def get_alt_words(word):
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

    # Find and capture markdown-style links to replace them
    link_patterns = {
        jd["name"]: re.compile(rf"\[([^]]*)\]\(#{jd['id']}\)") for jd in jdata
    }

    def defi_convert_links(defi):
        for name, r in link_patterns.items():
            # At least sdcv / koreader need the link target verbatim (not html escaped or url escaped)
            # https://github.com/ilius/pyglossary/issues/456
            defi = r.sub(
                rf"""<a class="dict-internal-link" href="bword://{name}">\1</a>""", defi
            )
        # markdown emphasis
        defi = re.sub(r"_([^ ]+)_", r"""<em class="dict-emphasis">\1</em>""", defi)
        return defi

    def backlinks(name: str):
        backlink_pattern = link_patterns[name]
        links = [
            f"""<a href="bword://{jd["name"]}">{jd["name"]}</a>"""
            for jd in jdata
            if backlink_pattern.search(jd["info"])
        ]
        if links:
            return dedent(
                f"""\
                <dl class="dict-backlinks">
                    <dt>Backlinks:</dt>
                    {"\n".join(f"<dd>{l}</dd>" for l in links)}
                </dl>
                """,
            )
        else:
            return ""

    glos = Glossary()

    for d in jdata:
        glos.addEntry(
            glos.newEntry(
                [d["name"], *get_alt_words(d["name"])],
                dedent(
                    f"""\
                    <link rel="stylesheet" type="text/css" href="{output_basename}.css"/>
                    <div>
                    <div class="dict-origin">{booktitle}, {d["chapter"]}</div>
                    <div class="dict-definition">{defi_convert_links(d["info"])}</div>
                    <hr>
                    <div class="dict-backlinks">{backlinks(d["name"])}</div>
                    </div>
                    """,
                ),
                defiFormat="h",  # "m" for plain text, "h" for HTML
            )
        )

    glos.setInfo("title", f"Wheel of Time Compendium {booknumber}: {booktitle}")
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

                .dict-backlinks > dt {
                    font-size: smaller;
                    font-weight: bold;
                }

                .dict-backlinks > dd {
                    font-size: smaller;
                    font-style: italic;
                }

                .dict-internal-link {}

                .dict-emphasis {}
                """,
            )
        )


books = {
    "00": "New Spring",
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
for num, name in books.items():
    print(f"Converting {num} {name}")
    write_dict(
        f"assets/data/book-{num}.json",
        f"wot-book-{num}",
        num,
        name,
    )
