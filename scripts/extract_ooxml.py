#!/usr/bin/env python3
"""Extract ordered text runs and embedded images from DOCX or PPTX using stdlib."""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def xml_from(zf: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(zf.read(name))
    except KeyError:
        return None


def relationship_map(zf: zipfile.ZipFile, owner: str) -> dict[str, str]:
    directory, filename = posixpath.split(owner)
    rel_file = posixpath.join(directory, "_rels", filename + ".rels")
    root = xml_from(zf, rel_file)
    result: dict[str, str] = {}
    if root is None:
        return result
    for rel in root.findall(q(PKG, "Relationship")):
        if rel.get("TargetMode") == "External":
            continue
        target = posixpath.normpath(posixpath.join(directory, rel.get("Target", "")))
        if target in zf.namelist() and not target.startswith("../"):
            result[rel.get("Id", "")] = target
    return result


def enabled(el: ET.Element | None, attr: str = "val") -> bool | None:
    if el is None:
        return None
    value = el.get(q(W, attr), "1")
    return value.lower() not in {"0", "false", "off", "none", "nil"}


def write_asset(zf: zipfile.ZipFile, target: str, assets: Path, ordinal: int) -> str:
    if not target.startswith(("word/media/", "ppt/media/")):
        raise ValueError(f"Image relationship points outside Office media: {target}")
    suffix = Path(target).suffix.lower()
    filename = f"image-{ordinal:04d}{suffix}"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / filename).write_bytes(zf.read(target))
    return filename


class Collector:
    def __init__(self, zf: zipfile.ZipFile, assets: Path, output: Path):
        self.zf = zf
        self.assets = assets
        self.output = output
        self.blocks: list[dict] = []
        self.image_count = 0

    def add_text(self, runs: list[dict], location: str, **extra: object) -> None:
        text = "".join(run["text"] for run in runs)
        if not text.strip():
            return
        self.blocks.append({"id": f"b{len(self.blocks)+1:04d}", "kind": "text", "location": location,
                            "text": text, "runs": runs, **extra})

    def add_image(self, target: str, location: str, alt: str = "", **extra: object) -> None:
        self.image_count += 1
        filename = write_asset(self.zf, target, self.assets, self.image_count)
        relative = posixpath.relpath(self.assets.resolve().as_posix(), self.output.parent.resolve().as_posix())
        asset = posixpath.join(relative, filename)
        self.blocks.append({"id": f"b{len(self.blocks)+1:04d}", "kind": "image", "location": location,
                            "asset": asset, "alt": alt, **extra})


def docx_styles(zf: zipfile.ZipFile) -> tuple[dict[str, ET.Element], dict[str, bool]]:
    root = xml_from(zf, "word/styles.xml")
    if root is None:
        return {}, {"bold": False, "underline": False}
    styles = {s.get(q(W, "styleId"), ""): s for s in root.findall(q(W, "style"))}
    defaults = root.find(f"{q(W,'docDefaults')}/{q(W,'rPrDefault')}/{q(W,'rPr')}")
    result = {"bold": False, "underline": False}
    if defaults is not None:
        for key, tag in [("bold", "b"), ("underline", "u")]:
            value = enabled(defaults.find(q(W, tag)))
            if value is not None:
                result[key] = value
    return styles, result


def docx_style_flags(style_id: str, styles: dict[str, ET.Element], defaults: dict[str, bool]) -> dict[str, bool]:
    flags = defaults.copy()
    lineage: list[ET.Element] = []
    seen: set[str] = set()
    while style_id and style_id in styles and style_id not in seen:
        seen.add(style_id)
        style = styles[style_id]
        lineage.append(style)
        parent = style.find(q(W, "basedOn"))
        style_id = parent.get(q(W, "val"), "") if parent is not None else ""
    for style in reversed(lineage):
        props = style.find(q(W, "rPr"))
        if props is None:
            continue
        for key, tag in [("bold", "b"), ("underline", "u")]:
            value = enabled(props.find(q(W, tag)))
            if value is not None:
                flags[key] = value
    return flags


def docx_paragraph(p: ET.Element, styles: dict[str, ET.Element], defaults: dict[str, bool]) -> tuple[list[dict], str, list[tuple[str, str]]]:
    p_style = p.find(f"{q(W,'pPr')}/{q(W,'pStyle')}")
    style_id = p_style.get(q(W, "val"), "Normal") if p_style is not None else "Normal"
    base = docx_style_flags(style_id, styles, defaults)
    runs: list[dict] = []
    for run in p.iter(q(W, "r")):
        pieces: list[str] = []
        for child in run:
            if child.tag == q(W, "t"):
                pieces.append(child.text or "")
            elif child.tag == q(W, "tab"):
                pieces.append("\t")
            elif child.tag in {q(W, "br"), q(W, "cr")}:
                pieces.append("\n")
        if not pieces:
            continue
        flags = base.copy()
        props = run.find(q(W, "rPr"))
        if props is not None:
            char_style = props.find(q(W, "rStyle"))
            if char_style is not None:
                flags = docx_style_flags(char_style.get(q(W, "val"), ""), styles, flags)
            for key, tag in [("bold", "b"), ("underline", "u")]:
                value = enabled(props.find(q(W, tag)))
                if value is not None:
                    flags[key] = value
        runs.append({"text": "".join(pieces), **flags})
    images: list[tuple[str, str]] = []
    for blip in p.iter(q(A, "blip")):
        rid = blip.get(q(R, "embed"))
        if rid:
            images.append((rid, ""))
    # Older Word files may use VML instead of DrawingML.
    for element in p.iter():
        if element.tag.rsplit("}", 1)[-1] == "imagedata":
            rid = element.get(q(R, "id"))
            if rid:
                images.append((rid, ""))
    docpr = next(p.iter(q(WP, "docPr")), None)
    if docpr is not None and images:
        images = [(rid, docpr.get("descr") or docpr.get("title") or "") for rid, _ in images]
    return runs, style_id, images


def docx_blocks(zf: zipfile.ZipFile, collector: Collector, paragraph_range: tuple[int, int] | None) -> None:
    root = xml_from(zf, "word/document.xml")
    if root is None:
        raise ValueError("DOCX has no word/document.xml")
    styles, defaults = docx_styles(zf)
    rels = relationship_map(zf, "word/document.xml")
    body = root.find(q(W, "body"))
    if body is None:
        raise ValueError("DOCX document body is missing")
    paragraphs: list[ET.Element] = []
    for child in body:
        if child.tag == q(W, "p"):
            paragraphs.append(child)
        elif child.tag == q(W, "tbl"):
            paragraphs.extend(child.iter(q(W, "p")))
    for index, p in enumerate(paragraphs, 1):
        if paragraph_range and not (paragraph_range[0] <= index <= paragraph_range[1]):
            continue
        runs, style, images = docx_paragraph(p, styles, defaults)
        location = f"段落 {index}"
        collector.add_text(runs, location, style=style)
        for rid, alt in images:
            target = rels.get(rid)
            if target:
                collector.add_image(target, location, alt=alt)


def slide_files(zf: zipfile.ZipFile) -> list[str]:
    presentation = xml_from(zf, "ppt/presentation.xml")
    rels = relationship_map(zf, "ppt/presentation.xml")
    if presentation is not None:
        files = []
        for slide in presentation.findall(f"{q(P,'sldIdLst')}/{q(P,'sldId')}"):
            target = rels.get(slide.get(q(R, "id"), ""))
            if target and re.fullmatch(r"ppt/slides/slide\d+\.xml", target):
                files.append(target)
        if files:
            return files
    return sorted((name for name in zf.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                  key=lambda name: int(re.search(r"slide(\d+)\.xml", name).group(1)))


def pptx_paragraph(p: ET.Element) -> list[dict]:
    defaults = p.find(f"{q(A,'pPr')}/{q(A,'defRPr')}")
    runs = []
    for item in p:
        if item.tag not in {q(A, "r"), q(A, "fld"), q(A, "br")}:
            continue
        if item.tag == q(A, "br"):
            runs.append({"text": "\n", "bold": False, "underline": False})
            continue
        text_element = item.find(q(A, "t"))
        if text_element is None or not (text_element.text or ""):
            continue
        props = item.find(q(A, "rPr"))
        if props is None:
            props = defaults
        bold = props is not None and props.get("b", "0") in {"1", "true"}
        underline = props is not None and props.get("u", "none") not in {"none", "0", "false"}
        runs.append({"text": text_element.text, "bold": bool(bold), "underline": bool(underline)})
    return runs


def pptx_blocks(zf: zipfile.ZipFile, collector: Collector, selected_slides: set[int] | None) -> None:
    slides = slide_files(zf)
    if not slides:
        raise ValueError("PPTX contains no editable slides")
    for slide_number, filename in enumerate(slides, 1):
        if selected_slides is not None and slide_number not in selected_slides:
            continue
        root = xml_from(zf, filename)
        if root is None:
            continue
        rels = relationship_map(zf, filename)
        tree = root.find(f"{q(P,'cSld')}/{q(P,'spTree')}")
        if tree is None:
            continue
        location = f"幻灯片 {slide_number}"

        def visit(shape: ET.Element) -> None:
            if shape.tag == q(P, "sp"):
                nonvisual = shape.find(f"{q(P,'nvSpPr')}/{q(P,'cNvPr')}")
                name = nonvisual.get("name", "") if nonvisual is not None else ""
                for para in shape.findall(f"{q(P,'txBody')}/{q(A,'p')}"):
                    collector.add_text(pptx_paragraph(para), location, slide=slide_number, shape=name)
            elif shape.tag == q(P, "pic"):
                nonvisual = shape.find(f"{q(P,'nvPicPr')}/{q(P,'cNvPr')}")
                alt = (nonvisual.get("descr") or nonvisual.get("name") or "") if nonvisual is not None else ""
                blip = next(shape.iter(q(A, "blip")), None)
                target = rels.get(blip.get(q(R, "embed"), "")) if blip is not None else None
                if target:
                    collector.add_image(target, location, alt=alt, slide=slide_number)
            elif shape.tag == q(P, "graphicFrame"):
                # Tables have editable paragraphs; charts/SmartArt require visual review.
                for para in shape.iter(q(A, "p")):
                    collector.add_text(pptx_paragraph(para), location, slide=slide_number)
            elif shape.tag == q(P, "grpSp"):
                for child in shape:
                    visit(child)

        for child in tree:
            visit(child)


def parse_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+):(\d+)", value)
    if not match or int(match.group(1)) < 1 or int(match.group(2)) < int(match.group(1)):
        raise argparse.ArgumentTypeError("Use START:END, with 1-based positive numbers")
    return int(match.group(1)), int(match.group(2))


def parse_slides(value: str) -> set[int]:
    result: set[int] = set()
    for piece in value.split(","):
        if "-" in piece:
            start, end = parse_range(piece.replace("-", ":"))
            result.update(range(start, end + 1))
        elif piece.isdecimal() and int(piece) > 0:
            result.add(int(piece))
        else:
            raise argparse.ArgumentTypeError("Use slide numbers such as 2-4,6")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="A .docx or .pptx file")
    parser.add_argument("--out", required=True, type=Path, help="Output source.json")
    parser.add_argument("--assets", required=True, type=Path, help="Directory for extracted images")
    parser.add_argument("--paragraphs", type=parse_range, help="DOCX paragraph range START:END (1-based)")
    parser.add_argument("--slides", type=parse_slides, help="PPTX slide numbers, e.g. 2-4,6")
    args = parser.parse_args()
    suffix = args.input.suffix.lower()
    if suffix not in {".docx", ".pptx"}:
        parser.error("Input must be .docx or .pptx")
    if suffix == ".docx" and args.slides is not None or suffix == ".pptx" and args.paragraphs is not None:
        parser.error("--paragraphs applies to DOCX; --slides applies to PPTX")
    if not args.input.is_file():
        parser.error(f"File not found: {args.input}")
    if not args.assets.resolve().is_relative_to(args.out.parent.resolve()):
        parser.error("--assets must be inside the directory containing --out")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(args.input) as zf:
            collector = Collector(zf, args.assets, args.out)
            if suffix == ".docx":
                docx_blocks(zf, collector, args.paragraphs)
            else:
                pptx_blocks(zf, collector, args.slides)
            if not collector.blocks:
                raise ValueError("No text or images found in the selected scope")
            payload = {"format": suffix[1:], "source": args.input.name, "blocks": collector.blocks}
            args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Extracted {len(collector.blocks)} blocks, including {collector.image_count} images → {args.out}")
            return 0
    except (zipfile.BadZipFile, ET.ParseError, ValueError, OSError) as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
