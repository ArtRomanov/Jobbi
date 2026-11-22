import pytest

from app.discovery.prefilter import excluded


@pytest.mark.parametrize(
    ("text", "terms", "expected"),
    [
        ("Senior Java developer", ["java"], True),
        ("Senior JavaScript developer", ["java"], False),
        ("Java/Kotlin backend", ["java"], True),
        ("JAVA engineer", ["java"], True),
        ("Work: office only, Berlin", ["office only"], True),
        ("Office, only for seniors", ["office only"], False),
        ("Our office is great, only remote", ["office only"], False),
        ("office   only", ["office only"], True),
        ("office\nonly", ["office only"], True),
        ("Офис в Москве, только офис", ["офис"], True),
        ("Офисный работник", ["офис"], False),
        ("ОФИС ТОЛЬКО", ["офис только"], True),
        ("Работа в аутсорсе", ["аутсорс"], False),
        ("C++ developer", ["c++"], True),
        ("C developer", ["c++"], False),
        ("Senior .NET engineer", [".net"], True),
        ("Anything", [], False),
        ("Anything", ["", "   "], False),
        ("Remote React role", ["java", "php", "remote"], True),
    ],
)
def test_excluded_whole_word_match(text: str, terms: list[str], expected: bool) -> None:
    assert excluded(None, text, terms) is expected


def test_title_is_checked_too() -> None:
    assert excluded("PHP Developer", "Great team, remote", ["php"]) is True


def test_no_match_in_title_or_text() -> None:
    assert excluded("Frontend Developer", "React, remote", ["php"]) is False


def test_terms_with_surrounding_spaces_are_trimmed() -> None:
    assert excluded(None, "Java developer", ["  java  "]) is True


def test_regex_metacharacters_are_literal() -> None:
    assert excluded(None, "a.b developer", ["a*b"]) is False
