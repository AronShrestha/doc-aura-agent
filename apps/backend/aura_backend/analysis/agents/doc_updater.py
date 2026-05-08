"""Doc Updater Agent.

Given one existing canonical Markdown doc and the code changes that
touch the files this doc references, produce a *minimally edited*
version of the doc that reflects the code change.

This is **not** a regenerator. The agent is instructed to leave any
sentence/section that is not affected by the diff byte-identical, and
only change the parts the diff implies. Output is the full updated
Markdown so the diff component can render before/after side-by-side.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .clients import TextModelClient
from .parsing import markdown_from_text


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Aura's Documentation Updater Agent.

Input: one Markdown documentation file ("ORIGINAL"), the unified
diff(s) of source code that the file references, and the list of
"DIRECT artifacts" (symbol metadata: name, qualified_name, category,
source_file).

Task: emit an UPDATED version of the Markdown that reflects ONLY the
changes implied by the diff.

Hard rules:
1. RENAME RULE — if a Direct artifact's `name` differs from any
   pre-existing artifact at the same source location (i.e. the diff is
   a rename: `def trigger` → `def triggerrrr`), find EVERY occurrence of
   the old name (bare token, in code spans, in headings, in tables, in
   prose) and replace it with the new name. Do not skip prose mentions.
2. ADD RULE — if the diff adds fields/parameters/return values to an
   existing symbol, update the corresponding tables/lists/signatures
   inside the doc. Add ONLY the new entries; do not rephrase the rest.
3. REMOVE RULE — if the diff removes a symbol or field, delete its
   entries from the doc. Don't restructure surrounding content.
4. SIGNATURE RULE — if a function/class signature changes (parameters,
   return type, decorators), update the signature wherever it appears
   verbatim in the doc.
5. NO-CHANGE RULE — if the diff implies nothing about this doc, return
   the ORIGINAL byte-for-byte. No reformatting, no rewording.

Forbidden:
- Rephrasing or restyling unaffected sentences.
- Adding new examples, rationale, or commentary not derivable from the
  diff.
- Removing or reordering unrelated headings/sections/tables.
- Wrapping output in code fences or markdown front matter that wasn't
  in the original.

Output: the FULL updated Markdown only. No prologue, no epilogue, no
explanation."""


async def update_doc_for_change(
    llm: TextModelClient,
    original_md: str,
    code_patches: dict[str, str],
    direct_artifacts: list[dict[str, Any]],
) -> str:
    """Return updated Markdown for one doc, minimally edited from ``original_md``.

    Args:
        llm: text model client.
        original_md: full Markdown of the existing canonical doc.
        code_patches: ``{source_file: unified_patch_str}`` for files that
            this doc references AND that the PR changed.
        direct_artifacts: list of artifact summary dicts (artifact_id,
            category, name, source_file, source_line_start) that are in
            the PR's Direct set and intersect this doc.
    """
    if not code_patches:
        return original_md
    user_payload = {
        "original_markdown": original_md,
        "direct_artifacts": direct_artifacts,
        "code_patches": code_patches,
    }
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_payload, sort_keys=True)},
    ]
    try:
        raw = await llm.complete(messages, temperature=0.1)
    except Exception as exc:
        logger.warning("doc updater llm failed; keeping original", extra={"event": "doc_update_failed", "error": str(exc)})
        return original_md
    updated = markdown_from_text(raw).strip()
    if not updated:
        return original_md
    return updated
