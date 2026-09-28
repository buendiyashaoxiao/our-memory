from memory_museum.importer import dedupe_key, import_chat
from memory_museum.parsers import ParsedMessage

from .conftest import write_json


def count(conn, sql="SELECT COUNT(*) FROM messages"):
    return conn.execute(sql).fetchone()[0]


def test_reimport_is_idempotent(conn, small_archive):
    first = import_chat(conn, [small_archive["chat"]])
    n = count(conn)
    second = import_chat(conn, [small_archive["chat"]])
    assert first.imported == n and n > 0
    assert second.imported == 0 and second.duplicates == n
    assert count(conn) == n


def test_duplicate_ids_are_skipped(conn, tmp_path):
    rec = {"id": "x", "time": "2024-01-01 10:00", "sender": "A", "text": "hi"}
    write_json(tmp_path / "d.json", [rec, dict(rec), {**rec, "id": "y"}])
    rep = import_chat(conn, [tmp_path / "d.json"])
    assert rep.imported == 2 and rep.duplicates == 1


def test_identical_messages_without_ids_are_both_kept(conn, tmp_path):
    p = tmp_path / "t.txt"
    p.write_text("2024-01-01 10:00 A: 好\n2024-01-01 10:00 A: 好\n", encoding="utf-8")
    rep = import_chat(conn, [p])
    assert rep.imported == 2
    assert import_chat(conn, [p]).imported == 0  # but not duplicated on re-import


def test_dedupe_key_prefers_source_id():
    m = ParsedMessage(sender_id="a", sender_display_name="a", timestamp=None, message_type="text", text="x",
                      source_message_id="1")
    other = ParsedMessage(sender_id="b", sender_display_name="b", timestamp=None, message_type="text", text="y",
                          source_message_id="1")
    assert dedupe_key(m) == dedupe_key(other)
    m.source_message_id = other.source_message_id = None
    assert dedupe_key(m) != dedupe_key(other)
    assert dedupe_key(m, 0) != dedupe_key(m, 1)


def test_name_only_senders_merge_into_id_based_participant(conn, tmp_path):
    write_json(tmp_path / "a.json", [{"id": 1, "time": "2024-01-01 10:00", "sender_id": "xia", "sender_name": "林夏",
                                      "text": "hi"}])
    (tmp_path / "b.txt").write_text("2024-01-02 10:00 林夏: 你好\n", encoding="utf-8")
    import_chat(conn, [tmp_path / "a.json", tmp_path / "b.txt"])
    ids = [r[0] for r in conn.execute("SELECT DISTINCT sender_id FROM messages")]
    assert ids == ["xia"]
    assert [r[0] for r in conn.execute("SELECT id FROM participants")] == ["xia"]


def test_replies_are_resolved(conn, tmp_path):
    write_json(tmp_path / "r.json", [
        {"id": "1", "time": "2024-01-01 10:00", "sender": "A", "text": "question"},
        {"id": "2", "time": "2024-01-01 10:01", "sender": "B", "text": "answer", "reply_to": "1"},
    ])
    import_chat(conn, [tmp_path / "r.json"])
    row = conn.execute("SELECT reply_to_message_id FROM messages WHERE source_message_id = '2'").fetchone()
    assert row[0] == conn.execute("SELECT id FROM messages WHERE source_message_id = '1'").fetchone()[0]


def test_unsupported_files_are_reported(conn, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "x.pdf").write_bytes(b"%PDF")
    rep = import_chat(conn, [src])
    assert rep.issue_counts["unsupported_file"] == 1


def test_undated_messages_are_kept_but_have_no_day(conn, tmp_path):
    write_json(tmp_path / "u.json", [{"id": 1, "sender": "A", "text": "when?"}])
    import_chat(conn, [tmp_path / "u.json"])
    assert conn.execute("SELECT day FROM messages").fetchone()[0] is None
