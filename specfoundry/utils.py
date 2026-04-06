"""Shared utilities."""
from __future__ import annotations

import json
import re


def extract_json(text: str) -> dict | list | None:
    """Extract the first valid JSON object or array from an LLM response.

    Handles:
    - Raw JSON
    - JSON inside ```json ... ``` fences
    - JSON inside ``` ... ``` fences
    - JSON embedded in surrounding prose
    """
    # 1. Try fenced code block
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass

    # 2. Try raw parse of the whole response
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 3. Find the largest balanced { ... } block
    for match in re.finditer(r"\{", text):
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    # 4. Find the largest balanced [ ... ] block
    for match in re.finditer(r"\[", text):
        start = match.start()
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break

    return None


def slugify(text: str) -> str:
    """Convert text to a safe directory/filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "project"
