"""Normalising agent output to points.

Agents ask the model for JSON arrays now, so `as_list` is mostly a
pass-through. It still has to cope with two things it can't control: Decision
Records written before the schema change, which hold these fields as one
paragraph, and a model that ignores the schema and returns a string anyway.
Neither may lose the founder's content.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents._text import as_list, as_text


def test_a_real_list_passes_through():
    assert as_list(["Margin fell to 4%.", "Churn doubled."]) == ["Margin fell to 4%.", "Churn doubled."]


def test_blank_entries_are_dropped_and_whitespace_collapsed():
    # Groq pads array entries with newlines often enough to matter.
    assert as_list(["  Margin\n  fell.  ", "", "   "]) == ["Margin fell."]


def test_nothing_becomes_an_empty_list():
    assert as_list(None) == []
    assert as_list("") == []
    assert as_list([]) == []


def test_a_legacy_numbered_paragraph_still_splits():
    # How company_formation wrote registration_steps before the change.
    older = "1. Reserve the name on MCA. 2. File SPICe+ Part B. 3. Apply for PAN and TAN."
    assert as_list(older) == [
        "Reserve the name on MCA",
        "File SPICe+ Part B",
        "Apply for PAN and TAN",
    ]


def test_an_unstructured_paragraph_is_kept_whole_not_chopped():
    # The important half of the contract: when there's no clear structure,
    # the founder's text survives intact as one point rather than being cut
    # mid-thought to look tidy.
    body = "Price near Rs 899 because that is what the order history shows customers pay."
    assert as_list(body) == [body]


def test_a_model_that_ignored_the_schema_still_renders():
    # A string where the schema asked for an array -- seen on Groq's free tier.
    reply = "Revenue grew 18% year on year; net margin fell to 4% on higher delivery cost."
    assert as_list(reply) == [
        "Revenue grew 18% year on year",
        "net margin fell to 4% on higher delivery cost.",
    ]


def test_as_text_numbers_points_so_a_model_reads_the_separations():
    # Prompt context: the model downstream must see the same breaks the
    # founder sees, not one run-on paragraph.
    assert as_text(["Margin fell.", "Churn doubled."]) == "1. Margin fell. 2. Churn doubled."


def test_as_text_leaves_a_single_point_unnumbered():
    assert as_text(["Margin fell."]) == "Margin fell."


def test_as_text_passes_a_plain_string_through():
    assert as_text("Margin fell.") == "Margin fell."
    assert as_text(None) == ""
