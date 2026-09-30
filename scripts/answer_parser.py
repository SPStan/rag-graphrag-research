"""Helpers for extracting the explicit final answer from reader output."""

import re


def extract_reader_answer(raw_response):
    """Extract one explicit final-answer marker; refuse ambiguous outputs."""
    matches = re.findall(r"(?i)\bAnswer:\s*(.*?)(?:\r?\n|$)", raw_response)
    if len(matches) > 1:
        return "", "ambiguous_answer_marker"
    if not matches or not matches[0].strip():
        return "", "missing_answer_marker"
    return matches[0].strip(), "ok"
