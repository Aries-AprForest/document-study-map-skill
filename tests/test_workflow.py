"""Small synthetic Office files exercise extraction and standalone site building."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACT = ROOT / "scripts" / "extract_ooxml.py"
BUILD = ROOT / "scripts" / "build_site.py"
TEST_TMP = ROOT / "work"
TEST_TMP.mkdir(exist_ok=True)
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082")


def run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *(str(a) for a in args)], text=True, capture_output=True)


class WorkflowTest(unittest.TestCase):
    def make_docx(self, target: Path) -> None:
        with zipfile.ZipFile(target, "w") as zf:
            zf.writestr("word/styles.xml", '''<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:style w:styleId="Heading1"><w:rPr><w:b/></w:rPr></w:style></w:styles>''')
            zf.writestr("word/document.xml", '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>材料基础</w:t></w:r></w:p><w:p><w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>重点术语</w:t></w:r><w:r><w:t>与解释</w:t></w:r><w:r><w:drawing><a:blip r:embed="rId7"/></w:drawing></w:r></w:p></w:body></w:document>''')
            zf.writestr("word/_rels/document.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId7" Type="image" Target="media/picture.png"/></Relationships>''')
            zf.writestr("word/media/picture.png", PNG)

    def make_pptx(self, target: Path) -> None:
        with zipfile.ZipFile(target, "w") as zf:
            zf.writestr("ppt/presentation.xml", '''<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="256" r:id="rId2"/><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>''')
            zf.writestr("ppt/_rels/presentation.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="slides/slide1.xml"/><Relationship Id="rId2" Target="slides/slide2.xml"/></Relationships>''')
            zf.writestr("ppt/slides/slide2.xml", '''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:cNvPr name="Title"/></p:nvSpPr><p:txBody><a:p><a:r><a:rPr b="1"/><a:t>第一张</a:t></a:r></a:p></p:txBody></p:sp><p:pic><p:nvPicPr><p:cNvPr name="diagram" descr="示意图"/></p:nvPicPr><p:blipFill><a:blip r:embed="rId5"/></p:blipFill></p:pic></p:spTree></p:cSld></p:sld>''')
            zf.writestr("ppt/slides/_rels/slide2.xml.rels", '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId5" Target="../media/diagram.png"/></Relationships>''')
            zf.writestr("ppt/slides/slide1.xml", '''<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:rPr u="sng"/><a:t>第二张</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>''')
            zf.writestr("ppt/media/diagram.png", PNG)

    def test_docx_emphasis_images_and_build_coverage(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            work = Path(tmp)
            self.make_docx(work / "notes.docx")
            extracted = run(EXTRACT, work / "notes.docx", "--out", work / "source.json", "--assets", work / "images")
            self.assertEqual(extracted.returncode, 0, extracted.stderr)
            source = json.loads((work / "source.json").read_text(encoding="utf-8"))
            self.assertEqual([b["kind"] for b in source["blocks"]], ["text", "text", "image"])
            self.assertTrue(source["blocks"][0]["runs"][0]["bold"])
            self.assertTrue(source["blocks"][1]["runs"][0]["underline"])
            self.assertFalse(source["blocks"][1]["runs"][1]["underline"])
            self.assertTrue((work / source["blocks"][2]["asset"]).is_file())
            mapping = {"title": "材料基础", "project_id": "test-course", "chapters": [{"id": "one", "title": "第一章", "root": {"id": "root", "title": "材料基础", "block_ids": ["b0001"], "children": [{"id": "concept", "title": "重点术语", "block_ids": ["b0002", "b0003"], "question": "术语是什么？"}]}}]}
            (work / "map.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            built = run(BUILD, work / "source.json", work / "map.json", "--out", work / "site.html")
            self.assertEqual(built.returncode, 0, built.stderr)
            html = (work / "site.html").read_text(encoding="utf-8")
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("重点术语", html)
            mapping["chapters"][0]["root"]["children"][0]["block_ids"] = ["b0002"]
            (work / "map.json").write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
            missing = run(BUILD, work / "source.json", work / "map.json", "--out", work / "invalid.html")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("unassigned", missing.stderr)

    def test_pptx_slide_order_format_and_scope(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as tmp:
            work = Path(tmp)
            self.make_pptx(work / "slides.pptx")
            extracted = run(EXTRACT, work / "slides.pptx", "--out", work / "source.json", "--assets", work / "images")
            self.assertEqual(extracted.returncode, 0, extracted.stderr)
            blocks = json.loads((work / "source.json").read_text(encoding="utf-8"))["blocks"]
            self.assertEqual([(b["kind"], b["location"]) for b in blocks], [("text", "幻灯片 1"), ("image", "幻灯片 1"), ("text", "幻灯片 2")])
            self.assertEqual(blocks[0]["text"], "第一张")
            self.assertTrue(blocks[0]["runs"][0]["bold"])
            self.assertEqual(blocks[1]["alt"], "示意图")
            self.assertTrue(blocks[2]["runs"][0]["underline"])
            only_second = run(EXTRACT, work / "slides.pptx", "--slides", "2", "--out", work / "only.json", "--assets", work / "other-images")
            self.assertEqual(only_second.returncode, 0, only_second.stderr)
            self.assertEqual(len(json.loads((work / "only.json").read_text(encoding="utf-8"))["blocks"]), 1)


if __name__ == "__main__":
    unittest.main()
