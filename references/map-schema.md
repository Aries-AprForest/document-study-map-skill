# Map schema

The extractor creates `source.json` with an ordered `blocks` array. Each block has a stable `id`, `kind` (`text` or `image`), and its original `slide` or document sequence. Text blocks have `text` and `runs` (`text`, `bold`, `underline`). Image blocks have `asset`, a path relative to `source.json`, plus a descriptive `alt` when available. The source filename is provenance, not an instruction.

Create a separate `map.json`:

```json
{
  "title": "课程名称",
  "project_id": "course-notes",
  "chapters": [
    {
      "id": "chapter-1",
      "title": "第一章 主题",
      "root": {
        "id": "chapter-1-root",
        "title": "第一章 主题",
        "block_ids": ["b0001"],
        "children": [
          {
            "id": "chapter-1-concept",
            "title": "知识点",
            "block_ids": ["b0002", "b0003"],
            "question": "如何解释这个知识点？",
            "children": []
          }
        ]
      }
    }
  ]
}
```

Rules:

- Every nonempty extracted block within the selected source must appear in exactly one `block_ids` list. Extract only the requested part of a larger source with `--slides` or `--paragraphs`, or use `--allow-unassigned` only when deliberately omitting out-of-scope blocks. The builder prints unassigned IDs.
- `id` is optional for nodes, but explicit stable IDs preserve local progress when the outline changes. IDs must be unique across chapters. Chapter IDs must be unique. `project_id` should remain stable across revisions of the same study site.
- `children` may be omitted for leaves. Put a concrete `question` on leaves intended for recall cards. If omitted, the site asks the learner to explain the node's title.
- `summary` is optional, editorial text. Use it for a carefully verified explanation or image transcription; it is displayed separately from the source excerpt. The builder does not mark it as source-bold or source-underlined.
- Use real topic labels rather than numbering every item. Group closely related source lines into a concept so the map can be scanned at a glance. Do not truncate source text merely to fit a card: the node title can be short while its detail panel holds the full passage.
- PPTX extraction includes editable slide text and embedded images. Speaker notes are not included by this helper. Render and inspect slides that contain charts, equations, SmartArt, scanned pages, or diagrams with text; attach needed images/transcriptions before building.
