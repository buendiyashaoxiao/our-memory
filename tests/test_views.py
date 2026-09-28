"""Timeline grouping, Random Day, statistics, hidden items, favorites and moments."""

import random
from collections import Counter

import pytest

from memory_museum import curation
from memory_museum.association import associate
from memory_museum.importer import import_chat
from memory_museum.index import build_day_summary, build_index
from memory_museum.media.scanner import import_media
from memory_museum.random_day import day_weight, pick_random_day
from memory_museum.stats import compute_stats
from memory_museum.textstats import count_words, emojis, tokenize
from memory_museum.timeline import context_around, day_detail, day_messages, timeline_page, years_overview


@pytest.fixture
def museum(conn, paths, small_archive):
    import_chat(conn, [small_archive["chat"]])
    import_media(conn, [small_archive["media"]], paths)
    associate(conn)
    build_index(conn)
    return conn


def summary(conn, day):
    return conn.execute("SELECT * FROM day_summary WHERE day = ?", (day,)).fetchone()


# ------------------------------------------------------------------ timeline

def test_day_summary_grouping(museum):
    d = summary(museum, "2024-03-01")
    assert (d["msg_count"], d["photo_count"], d["voice_count"]) == (4, 1, 1)
    assert d["audio_seconds"] == pytest.approx(1.0, abs=0.05)
    assert d["first_ts"] == "2024-03-01T09:00:00" and d["last_ts"] == "2024-03-01T20:05:00"
    assert summary(museum, "2024-03-04")["photo_count"] == 1  # media-only day
    assert summary(museum, "2024-03-03")["longest_session_minutes"] == 7


def test_years_overview(museum):
    y = years_overview(museum)
    assert y[0]["year"] == 2024 and y[0]["months"][0]["month"] == 3
    assert y[0]["months"][0]["cover"].startswith("/api/media/")


def test_curated_timeline_skips_trivial_days(museum):
    curated = [d["day"] for d in timeline_page(museum)["items"]]
    everything = [d["day"] for d in timeline_page(museum, mode="all")["items"]]
    assert "2024-03-03" not in curated and "2024-03-03" in everything  # text-only, short
    assert "2024-03-01" in curated


def test_timeline_pagination(museum):
    first = timeline_page(museum, mode="all", limit=2)
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = timeline_page(museum, mode="all", limit=50, cursor=first["next_cursor"])
    days = [d["day"] for d in first["items"] + rest["items"]]
    assert days == sorted(set(days)) and rest["next_cursor"] is None
    desc = timeline_page(museum, mode="all", order="desc", limit=50)
    assert [d["day"] for d in desc["items"]] == sorted(days, reverse=True)


def test_day_detail_and_message_paging(museum):
    d = day_detail(museum, "2024-03-01")
    assert d["prev_day"] is None and d["next_day"] == "2024-03-02"
    assert len(d["media"]) == 1 and len(d["voices"]) == 1
    image_msg = next(m for m in d["messages"]["items"] if m["type"] == "image")
    assert image_msg["media"]["association"]["confidence"] == "exact"
    page = day_messages(museum, "2024-03-01", limit=3)
    assert len(page["items"]) == 3
    more = day_messages(museum, "2024-03-01", cursor=page["next_cursor"])
    assert len(more["items"]) == 1
    assert day_detail(museum, "not-a-date") is None


def test_context_around(museum):
    msgs = context_around(museum, "2024-03-01T20:00:00", before=1, after=1)
    assert [m["ts"] for m in msgs] == ["2024-03-01T20:00:00", "2024-03-01T20:05:00"]


def test_missing_media_message_has_no_media(museum):
    msgs = day_detail(museum, "2024-03-05")["messages"]["items"]
    assert msgs[0]["type"] == "image" and msgs[0]["media"] is None


# ------------------------------------------------------------------ random day

def test_random_day_only_picks_meaningful_days(museum):
    picks = {pick_random_day(museum, rng=random.Random(i)) for i in range(60)}
    assert picks <= {"2024-03-01", "2024-03-02", "2024-03-03", "2024-03-04", "2024-03-05"}
    assert "2024-03-01" in picks


def test_random_day_excludes_current_and_hidden(museum):
    curation.set_day_hidden(museum, "2024-03-01", True)
    for i in range(30):
        d = pick_random_day(museum, rng=random.Random(i), exclude="2024-03-02")
        assert d not in ("2024-03-01", "2024-03-02")


def test_random_day_weighting_prefers_rich_days(museum):
    rich = {"msg_count": 40, "photo_count": 5, "video_count": 1, "voice_count": 2}
    poor = {"msg_count": 5, "photo_count": 0, "video_count": 0, "voice_count": 0}
    cfg = {"mode": "weighted", "photo": 1, "voice": 1, "video": 1, "conversation": 1}
    assert day_weight(rich, cfg) > 3 * day_weight(poor, cfg)
    assert day_weight(rich, {"mode": "uniform"}) == day_weight(poor, {"mode": "uniform"}) == 1
    counts = Counter(pick_random_day(museum, rng=random.Random(i)) for i in range(400))
    assert counts["2024-03-01"] > counts["2024-03-05"]


def test_random_day_empty_archive(conn):
    assert pick_random_day(conn) is None


# ------------------------------------------------------------------ stats

def test_statistics_from_real_data(museum):
    s = compute_stats(museum, use_cache=False)
    assert s["totals"]["messages"] == 15 and s["totals"]["photos"] == 3 and s["totals"]["voices"] == 1
    assert s["busiest_day"] == {"day": "2024-03-03", "value": 8}
    assert s["peak_hour"] == 22
    assert sum(s["hours"]) == 15
    assert s["first_message"]["text"] == "早安"
    assert s["words"]["laugh_messages"] == 8
    assert {b["sender_id"] for b in s["by_sender"]} == {"a", "b"}
    assert compute_stats(museum)["totals"] == s["totals"]  # served from cache


def test_word_and_emoji_counting():
    assert "下雨" in tokenize("今天下雨了") or "今天下雨" in "".join(tokenize("今天下雨了"))
    assert "的" not in tokenize("我的天")
    assert emojis("好累😮‍💨😂") == ["😮‍💨", "😂"]
    assert tokenize("check https://example.com/x [图片] Hello hello", use_jieba=False) == ["check", "hello", "hello"]
    words = dict(count_words(["一起吃饭", "一起吃饭吧", "晚安"])["words"])
    assert all(n >= 1 for n in words.values())


# ------------------------------------------------------------------ hidden items & favorites

def test_hiding_a_day_removes_it_everywhere(museum):
    curation.set_day_hidden(museum, "2024-03-01", True)
    assert "2024-03-01" not in [d["day"] for d in timeline_page(museum, mode="all")["items"]]
    assert day_detail(museum, "2024-03-01")["messages"]["items"] == []
    assert compute_stats(museum)["totals"]["messages"] == 11
    curation.set_day_hidden(museum, "2024-03-01", False)
    assert compute_stats(museum)["totals"]["messages"] == 15


def test_hiding_media_and_messages_updates_summaries(museum):
    mid = museum.execute("SELECT id FROM media WHERE original_filename = 'IMG_20240301_195930.jpg'").fetchone()[0]
    curation.update_media(museum, mid, {"hidden": True})
    assert summary(museum, "2024-03-01")["photo_count"] == 0
    assert day_detail(museum, "2024-03-01")["media"] == []
    msg = museum.execute("SELECT id FROM messages WHERE text = '早安'").fetchone()[0]
    curation.set_message_hidden(museum, msg, True)
    assert summary(museum, "2024-03-01")["msg_count"] == 3


def test_favorites(museum):
    mid = museum.execute("SELECT id FROM media LIMIT 1").fetchone()[0]
    msg = museum.execute("SELECT id FROM messages WHERE text = '早安'").fetchone()[0]
    curation.set_favorite(museum, "media", mid, True)
    curation.set_favorite(museum, "message", msg, True)
    curation.set_favorite(museum, "day", "2024-03-01", True)
    curation.set_favorite(museum, "day", "2024-03-01", True)  # idempotent
    favs = curation.list_favorites(museum)
    assert sorted(f["kind"] for f in favs) == ["day", "media", "message"]
    assert "2024-03-03" not in [d["day"] for d in timeline_page(museum)["items"]]
    curation.set_favorite(museum, "day", "2024-03-03", True)
    assert "2024-03-03" in [d["day"] for d in timeline_page(museum)["items"]]  # favorites enter the curated view
    curation.set_favorite(museum, "media", mid, False)
    assert len(curation.list_favorites(museum, "media")) == 0
    with pytest.raises(ValueError):
        curation.set_favorite(museum, "planet", "1", True)


def test_media_title_note_and_date_override(museum):
    mid = museum.execute("SELECT id FROM media WHERE media_type = 'voice'").fetchone()[0]
    out = curation.update_media(museum, mid, {"title": " 一个普通的晚安 ", "note": "n"})
    assert (out["title"], out["note"]) == ("一个普通的晚安", "n")
    out = curation.update_media(museum, mid, {"ts": "2024-03-04 23:00"})
    assert (out["day"], out["ts_source"]) == ("2024-03-04", "manual")
    assert summary(museum, "2024-03-04")["voice_count"] == 1
    out = curation.update_media(museum, mid, {"ts": None})
    assert out["day"] == "2024-03-01"
    with pytest.raises(ValueError):
        curation.update_media(museum, mid, {"ts": "whenever"})


def test_moments_crud(museum):
    mid = museum.execute("SELECT id FROM media LIMIT 1").fetchone()[0]
    msg = museum.execute("SELECT id FROM messages LIMIT 1").fetchone()[0]
    m = curation.create_moment(museum, {"title": "第一次见面", "start_day": "2024-03-01",
                                        "items": [{"kind": "media", "ref": mid}]})
    assert m["counts"] == {"message": 0, "media": 1} and m["cover"]["id"] == mid
    curation.add_moment_item(museum, m["id"], "message", msg)
    full = curation.get_moment(museum, m["id"])
    assert len(full["messages"]) == 1 and len(full["media"]) == 1
    assert curation.update_moment(museum, m["id"], {"title": "改个名字", "end_day": "2024-03-02"})["end_day"] == "2024-03-02"
    assert day_detail(museum, "2024-03-02")["moments"][0]["title"] == "改个名字"
    with pytest.raises(ValueError):
        curation.create_moment(museum, {"title": "  "})
    with pytest.raises(ValueError):
        curation.add_moment_item(museum, m["id"], "message", 999999)
    assert curation.delete_moment(museum, m["id"])
    assert curation.list_moments(museum) == []
    assert museum.execute("SELECT COUNT(*) FROM moment_items").fetchone()[0] == 0


def test_rebuild_is_stable(museum):
    before = [tuple(r) for r in museum.execute("SELECT * FROM day_summary ORDER BY day")]
    build_day_summary(museum)
    assert [tuple(r) for r in museum.execute("SELECT * FROM day_summary ORDER BY day")] == before
