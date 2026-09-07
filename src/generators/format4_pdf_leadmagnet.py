"""Format 4 — structured PDF lead magnet (e.g. "108 Ideas", "99 Rules"),
rendered with WeasyPrint and closing on a promo/CTA page."""
from __future__ import annotations
import json
import uuid

from src.models import ContentTopic, RawContent
from src.ai_brain.llm_client import complete, extract_json
from src.ai_brain.persona import persona_prompt_block
from src.config import get_settings
from src.storage_client import upload_bytes

SYSTEM_PROMPT = "You write structured, scannable lead-magnet content (numbered lists/rules/ideas)."

PROMPT_TEMPLATE = """\
{persona_block}

Topic: {title}
Angle: {preview}
Core takeaway: {core_takeaway}

{custom_instructions}

Create a structured lead-magnet document (e.g. "101 Ideas" or "50 Rules" style
— pick an item count that fits the topic) built around this topic.

Respond ONLY with JSON of this shape (keep the JSON keys in English exactly as
shown; write every text VALUE in the OUTPUT LANGUAGE specified above):
{{
  "title": "e.g. 101 Ideas for ...",
  "subtitle": "one-line supporting subtitle",
  "items": ["item 1", "item 2", "..."],
  "cta": "closing call-to-action line for the promo page"
}}
"""

_HTML_TEMPLATE = """\
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Noto Sans Thai', 'Thonburi', 'Leelawadee UI', 'Helvetica Neue', Arial, sans-serif; color: #1a1a1a; margin: 0; }}
  .cover {{ padding: 120px 60px; text-align: center; }}
  .cover h1 {{ font-size: 36px; margin-bottom: 12px; }}
  .cover p {{ font-size: 16px; color: #555; }}
  .content {{ padding: 50px 60px; }}
  ol {{ font-size: 14px; line-height: 1.8; padding-left: 20px; }}
  .promo {{ page-break-before: always; padding: 120px 60px; text-align: center; background: #111; color: #fff; }}
  .promo h2 {{ font-size: 28px; }}
  .promo p {{ font-size: 16px; }}
</style>
</head>
<body>
  <div class="cover">
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
  <div class="content">
    <ol>
      {items_html}
    </ol>
  </div>
  <div class="promo">
    <h2>{persona_name}</h2>
    <p>{cta}</p>
  </div>
</body>
</html>
"""


def generate(topic: ContentTopic, raw_content: RawContent, persona: dict, custom_prompt: str = ""):
    # Imported lazily: WeasyPrint needs system libs (pango/cairo/gdk-pixbuf) that
    # aren't required just to import the rest of the app — see README setup notes.
    from weasyprint import HTML

    custom_instructions = f"Additional style/tone instructions: {custom_prompt}" if custom_prompt else ""
    prompt = PROMPT_TEMPLATE.format(
        persona_block=persona_prompt_block(persona),
        title=topic.title,
        preview=topic.preview,
        core_takeaway=topic.core_takeaway,
        custom_instructions=custom_instructions,
    )
    raw = complete(SYSTEM_PROMPT, prompt, json_mode=True)
    data = extract_json(raw)

    items_html = "\n".join(f"<li>{item}</li>" for item in data.get("items", []))
    html_doc = _HTML_TEMPLATE.format(
        title=data.get("title", topic.title),
        subtitle=data.get("subtitle", ""),
        items_html=items_html,
        persona_name=persona.get("persona_name", ""),
        cta=data.get("cta", ""),
    )

    pdf_bytes = HTML(string=html_doc).write_pdf()
    name = f"leadmagnet_{uuid.uuid4().hex[:12]}.pdf"

    url = upload_bytes(f"pdfs/{name}", pdf_bytes, "application/pdf")
    if url:
        extra = {"pdf_url": url}
    else:
        settings = get_settings()
        output_dir = settings.data_dir / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / name
        pdf_path.write_bytes(pdf_bytes)
        extra = {"pdf_path": str(pdf_path)}

    return data.get("title", topic.title), json.dumps(data, ensure_ascii=False), extra
