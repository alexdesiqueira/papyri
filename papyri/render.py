import json
import os
from collections import defaultdict
from functools import lru_cache
from types import ModuleType

from flask import Flask
from jinja2 import (Environment, FileSystemLoader, PackageLoader,
                    select_autoescape)
from velin import NumpyDocString

from numpydoc.docscrape import Parameter

from .config import base_dir, cache_dir, html_dir, ingest_dir
from .crosslink import SeeAlsoItem, resolve_
from .take2 import Paragraph
from .utils import progress

app = Flask(__name__)


@app.route("/<ref>")
def route(ref):
    if ref.endswith(".html"):
        ref = ref[:-5]
    if ref == "favicon.ico":
        return ""
    files = os.listdir(cache_dir)

    env = Environment(
        loader=FileSystemLoader("papyri"),
        autoescape=select_autoescape(["html", "tpl.j2"]),
    )
    env.globals["exists"] = exists
    env.globals["paragraph"] = paragraph
    template = env.get_template("core.tpl.j2")

    known_ref = [x.name[:-5] for x in cache_dir.glob("*")]
    html_dir.mkdir(exist_ok=True)
    with open(cache_dir / f"{ref}.json") as f:
        bytes_ = f.read()
    ndoc = load_one(bytes_)

    env.globals["resolve"] = resolve_(ref, known_ref)

    return render_one(template=template, ndoc=ndoc, qa=ref, ext="")


def serve():
    app.run()


def paragraph(lines):
    p = Paragraph.parse_lines(lines)
    acc = []
    for c in p.children:
        if type(c).__name__ == "Directive":
            if c.role == "math":
                acc.append(("Math", c))
            else:
                acc.append((type(c).__name__, c))
        else:
            acc.append((type(c).__name__, c))
    return acc


def render_one(template, ndoc, qa, ext):
    br = ndoc.backrefs
    if len(br) > 30:

        b2 = defaultdict(lambda: [])
        for ref in br:
            mod, _ = ref.split(".", maxsplit=1)
            b2[mod].append(ref)
        backrefs = (None, b2)
    else:
        backrefs = (br, None)
    return template.render(
        doc=ndoc,
        qa=qa,
        version="X.y.z",
        module=qa.split(".")[0],
        backrefs=backrefs,
        ext=ext,
    )


def load_one(bytes_):
    data = json.loads(bytes_)
    blob = NumpyDocString("")
    blob._parsed_data = data["_parsed_data"]
    blob._parsed_data["Parameters"] = [
        Parameter(a, b, c) for (a, b, c) in blob._parsed_data["Parameters"]
    ]
    blob.refs = data["refs"]
    blob.edata = data["edata"]
    blob.backrefs = data["backref"]
    blob.see_also = [SeeAlsoItem.from_json(**x) for x in data.get("see_also", [])]
    return blob


@lru_cache()
def exists(ref):

    if (cache_dir / f"{ref}.json").exists():
        return "exists"
    else:
        # if not ref.startswith(("builtins.", "__main__")):
        #    print(ref, "missing in", qa)
        return "missing"


def main():
    # nvisited_items = {}
    files = os.listdir(cache_dir)

    env = Environment(
        loader=FileSystemLoader("papyri"),
        autoescape=select_autoescape(["html", "tpl.j2"]),
    )
    env.globals["exists"] = exists
    env.globals["paragraph"] = paragraph
    template = env.get_template("core.tpl.j2")

    known_ref = [x.name[:-5] for x in (base_dir / "cache").glob("*")]

    html_dir.mkdir(exist_ok=True)
    for p, fname in progress(files, description="Rendering..."):
        qa = fname[:-5]
        try:
            with open(cache_dir / fname) as f:
                bytes_ = f.read()
                ndoc = load_one(bytes_)
                # nvisited_items[qa] = ndoc
        except Exception as e:
            raise RuntimeError(f"error with {f}") from e

        # for p,(qa, ndoc) in progress(nvisited_items.items(), description='Rendering'):
        with (html_dir / f"{qa}.html").open("w") as f:

            env.globals["resolve"] = resolve_(qa, known_ref)

            f.write(render_one(template=template, ndoc=ndoc, qa=qa, ext=".html"))