"""CRM message clean-up -- the code that fixes what the local model gets wrong
in its message drafts. No model involved."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.crm import FALLBACK_MESSAGE, normalise_message, personalise


def test_name_placeholders_in_any_style_become_one_style():
    assert normalise_message("Hi [Name], we miss you") == "Hi {name}, we miss you"
    assert normalise_message("Hi {Name}!") == "Hi {name}!"
    assert normalise_message("Hi <first name>, hello") == "Hi {name}, hello"
    assert normalise_message("Hi [Customer Name]") == "Hi {name}"


def test_a_sentence_with_an_unfillable_placeholder_is_dropped_whole():
    # Seen in a real run: removing just "[date]" left "join us before."
    text = normalise_message("We miss you! Get 20% off your next order if you join us before [date].")
    assert text == "Hi {name}, we miss you!"


def test_a_greeting_is_added_when_the_model_forgets_the_name():
    # Seen in a real run: every "personalised" preview came out identical.
    assert normalise_message("Your coffee is waiting!") == "Hi {name}, your coffee is waiting!"


def test_nothing_usable_falls_back_to_a_safe_message():
    assert normalise_message("Your order from [Date] is ready.") == FALLBACK_MESSAGE


def test_demeaning_sentences_are_dropped():
    assert normalise_message("Hi {name}, come back! Unlike the slum areas nearby, we deliver fresh.") == "Hi {name}, come back!"


def test_personalise_uses_the_first_name():
    assert personalise("Hi {name}, come back!", "Riya Nair") == "Hi Riya, come back!"
