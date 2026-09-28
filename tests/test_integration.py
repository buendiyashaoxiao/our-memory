"""End-to-end backend: chat import + media import + database + API + timeline output."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from memory_museum.api.app import create_app
from memory_museum.cli import main as cli_main
from memory_museum.config import Paths
from memory_museum.db import open_db
from memory_museum.pipeline import commit_staging, discard_staging, open_staging, run_import, totals

from .conftest import make_photo, write_json


@pytest.fixture(scope="module")
def api(demo_db):
    with TestClient(create_app(demo_db, frontend_dist=None)) as c:
        yield c


def test_demo_import_survives_every_deliberate_problem(demo_db):
    conn = open_db(demo_db.db)
    t = totals(conn)
    assert t["messages"] > 3000
    assert [p["id"] for p in t["participants"]] == ["xia", "yu"]
    assert t["first_day"] == "2025-03-01" and t["last_day"] == "2025-09-30"
    assert t["undated_messages"] == 3
    assert t["media_by_status"].get("corrupt") == 3
    assert t["duplicates"] == 2
    assert t["linked_by_confidence"]["exact"] > 100
    assert conn.execute("SELECT COUNT(*) FROM messages WHERE msg_type = 'unknown'").fetchone()[0] == 1
    conn.close()


def test_api_overview_and_timeline(api):
    o = api.get("/api/overview").json()
    assert o["has_data"] and o["totals"]["days"] > 150
    years = api.get("/api/timeline/years").json()
    assert years[0]["year"] == 2025 and len(years[0]["months"]) == 7
    page = api.get("/api/timeline", params={"limit": 5}).json()
    assert len(page["items"]) == 5 and page["next_cursor"]
    card = page["items"][0]
    assert {"day", "stats", "excerpts", "media", "voices", "favorite", "moments"} <= card.keys()
    nxt = api.get("/api/timeline", params={"limit": 5, "cursor": page["next_cursor"]}).json()
    assert nxt["items"][0]["day"] > card["day"]


def test_api_day_random_and_media(api):
    d = api.get("/api/days/2025-05-01").json()
    assert d["stats"]["photos"] >= 4 and d["media"] and d["voices"]
    photo = d["media"][0]
    assert api.get(photo["thumb"]).headers["content-type"] == "image/jpeg"
    r = api.get(photo["url"], headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.content) == 10
    ctx = api.get(f"/api/media/{photo['id']}/context").json()
    assert ctx["messages"] and all(m["day"] for m in ctx["messages"])
    rnd = api.get("/api/random-day", params={"exclude": "2025-05-01"}).json()
    assert rnd["day"] and rnd["day"] != "2025-05-01"
    assert api.get("/api/days/2025-13-01").status_code == 400


def test_api_sound_museum_and_gallery(api):
    s = api.get("/api/sounds").json()
    assert s["total"] >= 40 and s["items"][0]["waveform"]
    amr = [i for i in s["items"] if i["filename"].endswith(".amr")]
    assert amr and amr[0]["playable"]  # transcoded for browsers
    assert api.get(amr[0]["url"]).headers["content-type"] == "audio/mp4"
    g = api.get("/api/gallery", params={"kind": "video"}).json()
    assert g["items"] and all(i["type"] == "video" for i in g["items"])
    months = api.get("/api/gallery/months").json()
    assert months[0]["month"] == "2025-03"


def test_api_curation_roundtrip(api):
    s = api.get("/api/sounds", params={"limit": 1}).json()["items"][0]
    r = api.patch(f"/api/media/{s['id']}", json={"title": "一个普通的晚安", "note": "那天下雨"})
    assert r.json()["title"] == "一个普通的晚安"
    assert api.put(f"/api/favorites/media/{s['id']}").status_code == 200
    fav = api.get("/api/sounds", params={"favorites": True}).json()
    assert [i["id"] for i in fav["items"]] == [s["id"]]
    m = api.post("/api/moments", json={"title": "测试片段", "items": [{"kind": "media", "ref": s["id"]}]}).json()
    assert api.get(f"/api/moments/{m['id']}").json()["media"][0]["title"] == "一个普通的晚安"
    assert api.put("/api/favorites/day/not-a-day").status_code == 400
    assert api.delete(f"/api/moments/{m['id']}").status_code == 200


def test_api_review_and_manual_link(api):
    summary = api.get("/api/review/summary").json()
    assert summary["problems"] == 3 and summary["duplicates"] == 2
    item = api.get("/api/review/media", params={"filter": "unlinked"}).json()["items"][0]
    cands = api.get(f"/api/media/{item['id']}/candidates").json()
    assert cands
    linked = api.put(f"/api/media/{item['id']}/link", json={"message_id": cands[0]["id"]}).json()
    assert linked["association"]["method"] == "manual" and linked["message"]["id"] == cands[0]["id"]
    assert api.get("/api/review/summary").json()["manual"] >= 1


def test_api_stats_search_settings(api):
    st = api.get("/api/stats").json()
    assert st["totals"]["messages"] > 3000 and st["words"]["words"]
    assert api.get("/api/search", params={"q": "晚安"}).json()["items"]
    s = api.patch("/api/settings", json={"language": "en", "random_day": {"mode": "uniform"}}).json()
    assert s["language"] == "en" and s["random_day"]["mode"] == "uniform" and s["random_day"]["photo"] == 1.0
    assert api.get("/api/copy").json()["museumTitle"] == "Our Memory Museum"
    assert api.patch("/api/settings", json={"nope": 1}).status_code == 400
    api.patch("/api/settings", json={"language": "zh", "random_day": {"mode": "weighted"}})


def test_staged_import_preserves_user_data_and_can_be_discarded(tmp_path):
    paths = Paths(tmp_path / "data").ensure()
    write_json(tmp_path / "c1" / "a.json", [{"id": 1, "time": "2024-01-01 10:00", "sender": "A", "text": "一"}])
    staging = open_staging(paths)
    run_import(staging, paths, chat_inputs=[tmp_path / "c1"])
    staging.close()
    commit_staging(paths)
    conn = open_db(paths.db)
    conn.execute("INSERT INTO favorites(kind, ref, created_at) VALUES ('day', '2024-01-01', 'now')")
    conn.commit()
    conn.close()

    write_json(tmp_path / "c2" / "b.json", [{"id": 2, "time": "2024-01-02 10:00", "sender": "A", "text": "二"}])
    staging = open_staging(paths)
    run_import(staging, paths, chat_inputs=[tmp_path / "c2"])
    staging.close()
    discard_staging(paths)
    conn = open_db(paths.db)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 1
    conn.close()

    staging = open_staging(paths)
    run_import(staging, paths, chat_inputs=[tmp_path / "c2"])
    staging.close()
    commit_staging(paths)
    conn = open_db(paths.db)
    assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM favorites").fetchone()[0] == 1
    conn.close()
    assert not paths.staging_db.exists()


def test_cli_import_preview_and_purge_never_touch_sources(tmp_path, capsys):
    src = tmp_path / "private-data"
    write_json(src / "chat" / "a.json", [{"id": 1, "time": "2024-01-01 10:00", "sender": "A", "type": "image",
                                          "media": "IMG_20240101_095950.jpg"}])
    photo = make_photo(src / "media" / "IMG_20240101_095950.jpg", None)
    data = tmp_path / "data"
    assert cli_main(["import", "--data-dir", str(data), "--chat", str(src / "chat"), "--media", str(src / "media"),
                     "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Detected" in out and "Exact: 1" in out and "Dry run" in out
    assert cli_main(["import", "--data-dir", str(data), "--chat", str(src / "chat"), "--media", str(src / "media"),
                     "--yes"]) == 0
    assert (data / "museum.db").exists() and any((data / "cache" / "thumbs").rglob("*.jpg"))
    assert cli_main(["purge", "--data-dir", str(data), "--yes"]) == 0
    assert not (data / "museum.db").exists() and not (data / "cache").exists()
    assert photo.exists() and (src / "chat" / "a.json").exists()


def test_cli_missing_input(tmp_path, capsys):
    assert cli_main(["import", "--data-dir", str(tmp_path / "d"), "--chat", str(tmp_path / "nope")]) == 2


def test_serves_built_frontend_with_spa_fallback(tmp_path, demo_db):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>museum</html>")
    (dist / "assets" / "a.js").write_text("console.log(1)")
    with TestClient(create_app(demo_db, frontend_dist=dist)) as c:
        assert c.get("/timeline").text == "<html>museum</html>"
        assert c.get("/assets/a.js").text == "console.log(1)"
        assert c.get("/api/unknown").status_code == 404
        assert c.get("/../../etc/passwd").text == "<html>museum</html>"


def test_generated_stress_dataset_imports(tmp_path):
    from memory_museum.demo_gen import generate_stress

    out = tmp_path / "stress"
    generate_stress(out, messages=3000, photos=40, voices=10)
    paths = Paths(tmp_path / "data").ensure()
    staging = open_staging(paths)
    res = run_import(staging, paths, chat_inputs=[out / "chat"], media_inputs=[out / "media"])
    staging.close()
    assert res.totals["messages"] == 3000
    assert res.totals["linked_by_confidence"]["exact"] == 50
    assert Path(out / "chat" / "stress.jsonl").stat().st_size > 0
