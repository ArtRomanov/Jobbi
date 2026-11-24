import pytest

from app.discovery.keyword_filter import keyword_matches


@pytest.mark.parametrize(
    ("text", "keywords"),
    [
        ("Senior React developer", ["react"]),
        ("REACT dev", ["react"]),
        ("Stack: ReactJS, Redux", ["react"]),
        ("Ищем фронтенда в команду", ["фронт"]),
        ("Ищем ФРОНТЕНД-разработчика", ["фронтенд"]),
        ("Front-end engineer", ["front end"]),
        ("Front end engineer", ["front-end"]),
        ("Front -  end engineer", ["front end"]),
        ("We use Node.js and Next.js", ["next.js"]),
        ("#react #remote", ["react"]),
        ("C# developer", ["c#"]),
        ("Senior .NET developer", [".net"]),
        ("Python backend", ["java", "python"]),
    ],
)
def test_post_with_a_keyword_at_a_word_start_matches(
    text: str, keywords: list[str]
) -> None:
    assert keyword_matches(None, text, keywords)


@pytest.mark.parametrize(
    ("text", "keywords"),
    [
        ("Senior Java engineer", ["react"]),
        ("Preact and Inferno", ["react"]),
        ("Ищем бэкенд-разработчика", ["фронт"]),
        ("frontier markets analyst", ["front end"]),
        ("", ["react"]),
    ],
)
def test_post_without_a_keyword_does_not_match(text: str, keywords: list[str]) -> None:
    assert not keyword_matches(None, text, keywords)


def test_title_counts_too() -> None:
    assert keyword_matches("Frontend Developer", "Join our product team", ["frontend"])


def test_one_matching_line_keeps_a_digest() -> None:
    digest = "Вакансии дня:\n1. Java Senior\n2. Go Middle\n3. React Lead, remote\n4. QA"

    assert keyword_matches(None, digest, ["react"])


@pytest.mark.parametrize("keywords", [[], [""], ["   "], [" - "]])
def test_no_usable_keywords_lets_everything_through(keywords: list[str]) -> None:
    assert keyword_matches(None, "Senior Java engineer", keywords)


def test_regex_characters_in_keywords_are_literal() -> None:
    assert keyword_matches(None, "C++ developer", ["c++"])
    assert not keyword_matches(None, "Cxx developer", ["c.."])
