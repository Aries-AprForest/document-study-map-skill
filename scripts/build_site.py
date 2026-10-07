#!/usr/bin/env python3
"""Validate a curated map and build a standalone offline study website."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import sys
from pathlib import Path

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def nonempty_string(value: object, name: str) -> str:
    need(isinstance(value, str) and bool(value.strip()), f"{name} must be nonempty text")
    return value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="source.json from extract_ooxml.py")
    parser.add_argument("map", type=Path, help="Curated map.json")
    parser.add_argument("--out", required=True, type=Path, help="Final standalone HTML file")
    parser.add_argument("--allow-unassigned", action="store_true", help="Omit source blocks not assigned to map nodes")
    args = parser.parse_args()
    try:
        source = json.loads(args.source.read_text(encoding="utf-8-sig"))
        plan = json.loads(args.map.read_text(encoding="utf-8-sig"))
        need(isinstance(source, dict) and isinstance(source.get("blocks"), list), "Invalid source.json: missing blocks")
        blocks = source["blocks"]
        block_by_id = {}
        for block in blocks:
            need(isinstance(block, dict), "Every source block must be an object")
            bid = nonempty_string(block.get("id"), "block id")
            need(bid not in block_by_id, f"Duplicate source block ID: {bid}")
            need(block.get("kind") in {"text", "image"}, f"Unsupported block kind: {bid}")
            block_by_id[bid] = block
        need(isinstance(plan, dict), "map.json must be an object")
        title = nonempty_string(plan.get("title"), "map title")
        project_id = nonempty_string(plan.get("project_id"), "project_id")
        need(isinstance(plan.get("chapters"), list) and plan["chapters"], "map.json needs at least one chapter")

        assigned: set[str] = set()
        node_ids: set[str] = set()
        chapter_ids: set[str] = set()
        images: dict[str, dict] = {}

        def image_payload(block: dict) -> dict:
            asset = Path(nonempty_string(block.get("asset"), f"image {block['id']} asset"))
            need(not asset.is_absolute() and ".." not in asset.parts, f"Image asset must stay inside source directory: {asset}")
            source_dir = args.source.parent.resolve()
            absolute = (source_dir / asset).resolve()
            need(absolute.is_relative_to(source_dir), f"Image asset escapes source directory: {asset}")
            need(absolute.is_file(), f"Missing image: {absolute}")
            need(absolute.suffix.lower() in SUPPORTED_IMAGES,
                 f"{absolute.suffix} images cannot render reliably in a browser; convert {absolute.name} to PNG or JPEG")
            mime = mimetypes.guess_type(absolute.name)[0] or "image/png"
            need(mime.startswith("image/"), f"Unsupported image type: {absolute.name}")
            return {"src": "data:" + mime + ";base64," + base64.b64encode(absolute.read_bytes()).decode("ascii"),
                    "alt": block.get("alt") or "来源文件中的图片"}

        def compile_node(raw: dict, lineage: list[str]) -> dict:
            need(isinstance(raw, dict), "Every map node must be an object")
            node_title = nonempty_string(raw.get("title"), "node title")
            auto_id = "node-" + hashlib.sha256(" / ".join(lineage + [node_title]).encode()).hexdigest()[:12]
            node_id = nonempty_string(raw.get("id", auto_id), "node id")
            need(node_id not in node_ids, f"Duplicate node ID: {node_id}")
            node_ids.add(node_id)
            refs = raw.get("block_ids", [])
            need(isinstance(refs, list) and all(isinstance(r, str) for r in refs), f"{node_title}: block_ids must be strings")
            node_blocks = []
            important = False
            image_ids = []
            for ref in refs:
                need(ref in block_by_id, f"{node_title}: unknown source block {ref}")
                need(ref not in assigned, f"Source block {ref} is assigned more than once")
                assigned.add(ref)
                block = block_by_id[ref]
                if block["kind"] == "text":
                    runs = block.get("runs", [])
                    need(isinstance(runs, list), f"{ref}: runs must be a list")
                    for run in runs:
                        need(isinstance(run, dict) and isinstance(run.get("text"), str), f"{ref}: invalid text run")
                    important |= any((r.get("bold") or r.get("underline")) and r["text"].strip() for r in runs)
                    node_blocks.append({"kind": "text", "text": block.get("text", ""), "runs": runs,
                                        "location": block.get("location", "")})
                else:
                    if ref not in images:
                        images[ref] = image_payload(block)
                    image_ids.append(ref)
                    node_blocks.append({"kind": "image", "image_id": ref, "location": block.get("location", "")})
            children_raw = raw.get("children", [])
            need(isinstance(children_raw, list), f"{node_title}: children must be a list")
            children = [compile_node(child, lineage + [node_title]) for child in children_raw]
            summary = raw.get("summary", "")
            question = raw.get("question", "")
            need(isinstance(summary, str) and isinstance(question, str), f"{node_title}: summary/question must be text")
            return {"id": node_id, "title": node_title, "blocks": node_blocks, "children": children,
                    "important": bool(important), "key_count": int(bool(important)) + sum(c["key_count"] for c in children),
                    "image_ids": image_ids, "summary": summary, "question": question}

        chapters = []
        for raw_chapter in plan["chapters"]:
            need(isinstance(raw_chapter, dict), "Each chapter must be an object")
            cid = nonempty_string(raw_chapter.get("id"), "chapter id")
            need(cid not in chapter_ids, f"Duplicate chapter ID: {cid}")
            chapter_ids.add(cid)
            ctitle = nonempty_string(raw_chapter.get("title"), "chapter title")
            root = compile_node(raw_chapter.get("root"), [cid])
            all_nodes = []

            def visit(node: dict) -> None:
                all_nodes.append(node)
                for child in node["children"]:
                    visit(child)

            visit(root)
            leaves = [node for node in all_nodes if not node["children"]]
            need(leaves, f"{ctitle}: at least one leaf concept is required")
            chapters.append({"id": cid, "title": ctitle, "root": root,
                             "stats": {"nodes": len(all_nodes), "cards": len(leaves),
                                       "keys": sum(bool(n["important"]) for n in all_nodes[1:]),
                                       "images": len(set(i for n in all_nodes for i in n["image_ids"]))}})

        unassigned = [b["id"] for b in blocks if b["id"] not in assigned]
        if unassigned:
            message = f"{len(unassigned)} source blocks are unassigned: {', '.join(unassigned[:30])}"
            if not args.allow_unassigned:
                raise ValueError(message + ". Assign them or use --allow-unassigned for a deliberate subset.")
            print("Warning: " + message, file=sys.stderr)

        template = (Path(__file__).resolve().parent.parent / "assets" / "study-site.html").read_text(encoding="utf-8")
        need(template.count("__STUDY_MAP_DATA__") == 1, "Website template needs one data placeholder")
        payload = {"title": title, "project_id": project_id, "source": Path(source.get("source", "notes")).name,
                   "chapters": chapters, "images": images}
        embedded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        html = template.replace("__STUDY_MAP_DATA__", embedded).replace("__STUDY_MAP_TITLE__", title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html, encoding="utf-8")
        print(f"Built {args.out}: {len(chapters)} chapters, {sum(c['stats']['cards'] for c in chapters)} cards, {len(images)} images")
        return 0
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
