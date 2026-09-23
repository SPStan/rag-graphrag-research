"""Helpers for extracting the explicit final answer from reader output."""

import re


def extract_reader_answer(raw_response):
    """Extract the final explicit Answer marker, even when it follows inline text."""
    matches = re.findall(r"(?i)\bAnswer:\s*(.*?)(?:\r?\n|$)", raw_response)
    if not matches or not matches[-1].strip():
        return "", "missing_answer_marker"
    return matches[-1].strip(), "ok"
