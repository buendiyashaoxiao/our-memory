from datetime import datetime
from pathlib import Path

from memory_museum.parsers import ImportReport, detect_parser, get_parser
from memory_museum.parsers.base import normalize_type, split_marker

from .conftest import FIXTURES, write_json

CORRUPT = FIXTURES / "corrupted"


def parse(path: Path, name: str | None = None):
    rep = ImportReport()
    parser = get_parser(name) if name else detect_parser(path)
    return list(parser.parse(path, rep)), rep


def test_json_object_with_participants_normalizes_fields(tmp_path):
    p = write_json(tmp_path / "c.json", [
        {"msg_id": 7, "timestamp": "2024-01-02 03:04:05", "from_id": "u1", "content": "你好", "reply_to": 6},
        {"id": 8, "date": 1704164645, "sender_id": "u2", "msg_type": "图片", "attachment": {"filename": "a.jpg"}},
    ], participants=[{"id": "u1", "name": "One"}, {"id": "u2", "name": "Two"}], conversation_id="c1")
    msgs, rep = parse(p)
    assert [m.source_message_id for m in msgs] == ["7", "8"]
    assert msgs[0].sender_display_name == "One"
    assert msgs[0].timestamp == datetime(2024, 1, 2, 3, 4, 5)
    assert msgs[0].reply_to_message_id == "6"
    assert msgs[0].conversation_id == "c1"
    assert msgs[1].message_type == "image" and msgs[1].media_reference == "a.jpg"
    assert rep.records_seen == 2 and not rep.issue_counts


def test_json_array_and_type_inference(tmp_path):
    p = tmp_path / "a.json"
    p.write_text('[{"time": "2024-01-01 10:00", "sender": "A", "file": "clip.mp4"},'
                 ' {"time": "2024-01-01 10:01", "sender": "B", "text": "[语音] v.m4a 5\\""}]', encoding="utf-8")
    msgs, _ = parse(p)
    assert msgs[0].message_type == "video" and msgs[0].media_reference == "clip.mp4"
    assert msgs[1].message_type == "voice" and msgs[1].media_reference == "v.m4a" and msgs[1].text is None


def test_json_records_with_problems_are_reported_not_dropped(tmp_path):
    p = write_json(tmp_path / "p.json", [
        {"id": 1, "sender": "A", "text": "no time"},
        {"id": 2, "time": "someday", "sender": "A", "text": "bad time"},
        {"id": 3, "time": "2024-01-01 10:00", "sender": "A", "type": "red_packet", "text": "?"},
        "not an object",
        {"id": 5, "time": "2024-01-01 10:00", "sender": "A", "text": ""},
    ])
    msgs, rep = parse(p)
    assert [m.source_message_id for m in msgs] == ["1", "2", "3"]
    assert msgs[0].timestamp is None and msgs[1].timestamp is None
    assert msgs[1].metadata["raw_timestamp"] == "someday"
    assert msgs[2].message_type == "unknown" and msgs[2].metadata["raw_type"] == "red_packet"
    assert rep.issue_counts == {"missing_timestamp": 1, "bad_timestamp": 1, "unknown_type": 1, "malformed": 2}


def test_truncated_json_falls_back_to_line_mode(tmp_path):
    msgs, rep = parse(CORRUPT / "truncated.json")
    assert rep.issue_counts["unreadable_file"] == 1
    assert isinstance(msgs, list)  # no exception


def test_jsonl_with_bad_lines():
    msgs, rep = parse(CORRUPT / "mixed.jsonl")
    assert len(msgs) == 2
    assert rep.issue_counts["malformed"] == 1
    assert rep.issue_counts["missing_timestamp"] == 1


def test_csv_aliases_and_chinese_headers(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("时间,发送者,内容,类型,附件\n2024-01-01 10:00:00,阿林,早,文本,\n2024-01-01 10:01:00,小周,,图片,x.jpg\n",
                 encoding="utf-8-sig")
    msgs, rep = parse(p)
    assert [(m.sender_id, m.message_type) for m in msgs] == [("阿林", "text"), ("小周", "image")]
    assert msgs[1].media_reference == "x.jpg"
    assert not rep.issue_counts


def test_csv_gb18030_encoding(tmp_path):
    p = tmp_path / "gbk.csv"
    p.write_bytes("time,sender,text\n2024-01-01 10:00:00,阿林,你好世界\n".encode("gb18030"))
    msgs, _ = parse(p)
    assert msgs[0].text == "你好世界"


def test_malformed_csv_is_survivable():
    msgs, rep = parse(CORRUPT / "malformed.csv")
    assert msgs[0].text == "ok"
    assert rep.issue_counts["missing_timestamp"] >= 1


def test_txt_layouts(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text(
        "2024-03-01 21:03:15 林夏: 到家了吗\n"
        "第二行\n"
        "[2024-03-01 21:04] 周屿：到了\n"
        "2024-03-01 21:05:00 林夏\n"
        "这是块状格式\n"
        "———— 2024-03-02 ————\n"
        "08:00 周屿: 早\n"
        "08:01 林夏: [图片] IMG_1.jpg\n"
        "08:02 周屿: [表情]\n",
        encoding="utf-8",
    )
    msgs, rep = parse(p)
    assert [m.text for m in msgs[:3]] == ["到家了吗\n第二行", "到了", "这是块状格式"]
    assert msgs[3].timestamp == datetime(2024, 3, 2, 8, 0)
    assert msgs[4].message_type == "image" and msgs[4].media_reference == "IMG_1.jpg"
    assert msgs[5].message_type == "sticker"
    assert not rep.issue_counts


def test_txt_whatsapp_day_first_detection(tmp_path):
    p = tmp_path / "wa.txt"
    p.write_text("03/04/2024, 20:30 - A: first\n17/04/2024, 20:31 - B: second\n"
                 "17/04/2024, 20:32 - Messages are end-to-end encrypted.\n", encoding="utf-8")
    msgs, _ = parse(p)
    assert msgs[0].timestamp == datetime(2024, 4, 3, 20, 30)
    assert msgs[2].message_type == "system"


def test_txt_weird_file_reports_problems():
    msgs, rep = parse(CORRUPT / "weird.txt")
    assert msgs[0].text.startswith("hello")
    assert rep.issue_counts["malformed"] >= 1
    assert rep.issue_counts["bad_timestamp"] == 1


def test_type_normalization_and_markers():
    assert normalize_type("语音") == "voice"
    assert normalize_type("PHOTO") == "image"
    assert normalize_type("red_packet") is None
    assert split_marker("<Media omitted>")[0] == "image"
    assert split_marker("普通文字") == (None, None, "普通文字")


def test_detect_parser_by_extension(tmp_path):
    (tmp_path / "x.pdf").write_bytes(b"%PDF")
    assert detect_parser(tmp_path / "x.pdf") is None
