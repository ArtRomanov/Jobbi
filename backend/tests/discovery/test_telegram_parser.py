from datetime import datetime
from pathlib import Path

import pytest

from app.discovery.fetchers.telegram import MAX_TEXT_CHARS, parse_channel_page

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestRealPages:
    def test_telegram_channel_page(self) -> None:
        posts, oldest_id = parse_channel_page(_fixture("tg_telegram.html"), "telegram")

        assert len(posts) == 20
        assert oldest_id == 441
        first = posts[0]
        assert first.external_key == "tg:telegram/441"
        assert first.url == "https://t.me/telegram/441"
        assert first.posted_at == datetime(2026, 5, 14, 16, 8, 31)
        assert first.posted_at.tzinfo is None
        assert first.text.startswith("Bot-to-Bot Communication.")
        assert first.title is None and first.company is None

    def test_links_to_telegram_hosts_are_not_job_links(self) -> None:
        posts, _ = parse_channel_page(_fixture("tg_telegram.html"), "telegram")

        assert all(post.job_link is None for post in posts)

    def test_text_nested_inside_media_container_is_found(self) -> None:
        posts, _ = parse_channel_page(_fixture("tg_telegram.html"), "telegram")

        by_key = {post.external_key: post for post in posts}
        assert by_key["tg:telegram/450"].text.startswith("⭐️ Rich Text Editor.")

    def test_reply_quote_is_not_the_post_text(self) -> None:
        posts, _ = parse_channel_page(_fixture("tg_durov.html"), "durov")

        post = next(p for p in posts if p.external_key == "tg:durov/558")
        assert post.text.startswith("CORRECTION")
        assert "Unfair that CEOs" not in post.text

    def test_line_breaks_are_kept(self) -> None:
        posts, _ = parse_channel_page(_fixture("tg_durov.html"), "durov")

        assert any("\n" in post.text for post in posts)
        assert all("<br" not in post.text for post in posts)

    def test_channel_name_is_case_insensitive(self) -> None:
        posts, oldest_id = parse_channel_page(_fixture("tg_durov.html"), "Durov")

        assert oldest_id == 547
        assert posts[0].external_key == "tg:durov/547"


class TestCraftedPage:
    @pytest.fixture
    def parsed(self) -> dict[str, object]:
        posts, oldest_id = parse_channel_page(
            _fixture("tg_crafted_jobs.html"), "jobbi_test"
        )
        return {"posts": {p.external_key: p for p in posts}, "oldest_id": oldest_id}

    def test_only_this_channel_posts(self, parsed: dict) -> None:
        assert set(parsed["posts"]) == {
            "tg:jobbi_test/101",
            "tg:jobbi_test/102",
            "tg:jobbi_test/103",
        }
        assert parsed["oldest_id"] == 101

    def test_media_only_post(self, parsed: dict) -> None:
        post = parsed["posts"]["tg:jobbi_test/101"]
        assert post.text == ""
        assert post.job_link is None

    def test_external_job_link_is_first_non_telegram_link_normalized(
        self, parsed: dict
    ) -> None:
        post = parsed["posts"]["tg:jobbi_test/102"]
        assert post.job_link == "https://jobs.example.com/careers/123?ref=tg"

    def test_text_is_plain_with_line_breaks(self, parsed: dict) -> None:
        post = parsed["posts"]["tg:jobbi_test/102"]
        assert post.text.startswith(
            "Senior React Developer at Acme\nFully remote, €5000–6000\n\n"
        )
        assert "\n\n\n" not in post.text
        assert "<b>" not in post.text

    def test_timestamp_converted_to_naive_utc(self, parsed: dict) -> None:
        post = parsed["posts"]["tg:jobbi_test/102"]
        assert post.posted_at == datetime(2026, 11, 21, 7, 30)

    def test_reply_quote_link_and_telegram_links_ignored(self, parsed: dict) -> None:
        post = parsed["posts"]["tg:jobbi_test/103"]
        assert post.text.startswith("Update: the role is filled.")
        assert post.job_link is None


def test_text_is_capped() -> None:
    long_text = "x" * (MAX_TEXT_CHARS + 500)
    html = (
        '<div class="tgme_widget_message" data-post="jobbi_test/1">'
        f'<div class="tgme_widget_message_text js-message_text">{long_text}</div>'
        '<time datetime="2026-11-22T00:00:00+00:00"></time></div>'
    )
    posts, _ = parse_channel_page(html, "jobbi_test")
    assert len(posts[0].text) == MAX_TEXT_CHARS


def test_post_without_timestamp_is_skipped_but_counts_for_paging() -> None:
    html = '<div class="tgme_widget_message" data-post="jobbi_test/7"></div>'
    posts, oldest_id = parse_channel_page(html, "jobbi_test")
    assert posts == []
    assert oldest_id == 7


def test_empty_page() -> None:
    assert parse_channel_page("<html><body></body></html>", "jobbi_test") == ([], None)


@pytest.mark.parametrize("channel", ["../evil", "a/b", "ab", "x" * 33, "chan?x=1", ""])
def test_invalid_channel_name_rejected(channel: str) -> None:
    with pytest.raises(ValueError):
        parse_channel_page("", channel)
