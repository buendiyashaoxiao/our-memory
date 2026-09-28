# Import formats

The importer auto-detects the parser per file (extension + content sniffing). Force one with `--parser json|csv|txt`. List parsers with `python -m memory_museum parsers`.

All parsers produce the same normalized message:

| field | meaning |
| --- | --- |
| `conversation_id` | defaults to `main` (override with `--conversation`) |
| `sender_id`, `sender_display_name` | if only a name exists, the name is also the id |
| `timestamp` | naive local time (see *Timestamps*) or empty if unparseable — the message is kept but not placed on the timeline |
| `message_type` | text, image, voice, audio, video, sticker, file, link, system, unknown |
| `text` | message text (markers like `[图片] x.jpg` are removed from it) |
| `reply_to_message_id` | the export's id of the quoted message |
| `media_reference` | file name/path of the attachment |
| `source_file`, `source_message_id` | provenance |
| `metadata` | every other field from the record, plus `raw_type`/`raw_timestamp` when they could not be understood |

## JSON (`.json`, `.jsonl`, `.ndjson`)

```json
{
  "conversation_id": "main",
  "participants": [{"id": "xia", "name": "林夏"}, {"id": "yu", "name": "周屿"}],
  "messages": [
    {"id": "m1", "time": "2025-03-08 21:37:12", "sender_id": "xia", "type": "text", "text": "到家了"},
    {"id": "m2", "time": "2025-03-08 21:44:03", "sender_id": "yu", "type": "image", "media": "IMG_20250308_214143.jpg"},
    {"id": "m3", "time": 1741441500, "sender_id": "yu", "type": "voice", "media": "voice_1.m4a", "duration": 8,
     "reply_to": "m1"}
  ]
}
```

Also accepted: a bare array of message objects, and JSON Lines (one object per line — recommended for very large archives because it is streamed). A truncated/corrupt `.json` file is retried line by line and reported.

Recognised keys (case-insensitive; first match wins):

| meaning | keys |
| --- | --- |
| id | `id`, `message_id`, `msg_id`, `msgid`, `msgId`, `消息ID` |
| time | `timestamp`, `time`, `datetime`, `date`, `ts`, `created_at`, `createTime`, `create_time`, `sent_at`, `时间`, `发送时间`, `日期` |
| sender name | `sender_name`, `sender`, `from`, `author`, `name`, `talker`, `nickname`, `发送者`, `发送人`, `昵称` (may also be an object `{id, name}`) |
| sender id | `sender_id`, `from_id`, `user_id`, `author_id`, `uid`, `talker_id`, `发送者ID` |
| text | `text`, `content`, `message`, `body`, `msg`, `内容`, `消息` |
| type | `type`, `msg_type`, `message_type`, `kind`, `类型`, `消息类型` |
| attachment | `media`, `media_path`, `media_file`, `file`, `filename`, `attachment`, `path`, `photo`, `voice`, `video`, `附件`, `文件`, or `attachments: [...]` (first item; may be an object with `filename`/`path`/`uri`) |
| reply | `reply_to`, `reply_to_id`, `reply_to_message_id`, `quote_id`, `quoted_id`, `引用` |
| conversation | `conversation_id`, `chat_id`, `conversation`, `chat`, `会话` |
| voice length | `duration`, `voice_length`, `时长` |

Type labels understood: `text/文本/文字`, `image/photo/picture/img/图片/照片`, `voice/ptt/语音`, `audio/music/音频`, `video/视频/小视频`, `sticker/emoji/gif/表情/动画表情`, `file/document/文件`, `link/url/share/链接/分享`, `system/notice/recall/系统消息/撤回`, and WeChat's numeric codes `1, 3, 34, 43, 47, 49, 10000`. Anything else becomes `unknown` (kept, reported, original label in `metadata.raw_type`). Without a type, it is inferred from the attachment extension or a text marker.

## CSV / TSV (`.csv`, `.tsv`)

First row = header, same column aliases as JSON. Delimiter is sniffed (`,` `;` tab `|`). Rows with extra cells keep them in `metadata._extra` and are reported; empty rows are reported.

```csv
id,time,sender_id,sender,type,content,file,duration
m100,2025/08/01 08:12:00,xia,林夏,text,早,,
m101,2025/08/01 12:30:05,yu,周屿,image,,IMG_20250801_122955.jpg,
m102,2025/08/01 22:40:10,yu,周屿,voice,,voice_20250801_224010.m4a,6
```

## Plain text (`.txt`, `.log`)

Layouts can be mixed within a file:

```
2024-03-01 21:03:15 林夏: 到家了吗            ← inline (ASCII or full-width colon)
下一行会接在上一条消息后面                      ← continuation line
[2024-03-01 21:04] 周屿：到了                 ← bracketed
2024-03-01 21:05:00 林夏                     ← block header …
这是块状格式                                  ← … message body on the following lines
———————— 2024-03-02 ————————                ← date line (optionally with 星期X)
08:00 周屿: 早                               ← time-only lines use the last date line
08:01 林夏: [图片] IMG_20240302_080050.jpg   ← media marker with file name
08:02 周屿: [语音] voice_1.m4a 8"            ← voice marker (duration is ignored; read from the file)
08:03 林夏: [表情]
01/03/2024, 21:03 - 林夏: WhatsApp style     ← day/month order detected from the whole file
01/03/2024, 21:04 - Messages are end-to-end encrypted.   ← no sender → system message
```

Markers: `[图片] [照片] [语音] [视频] [表情] [动画表情] [文件] [链接] [音频] [Photo] [Image] [Voice] [Audio] [Video] [Sticker] [File] [Link]` (also with `【】` or `<>`), and `<Media omitted>`. Lines before the first recognisable header are reported as malformed.

## Timestamps

| input | result |
| --- | --- |
| `2024-03-01 21:03:15`, `2024/3/1 21:03`, `2024.03.01`, `2024-03-01T21:03` | as written (local time) |
| `2024-03-01 09:03 PM`, `2024年3月1日 下午3:05`, `2024年3月1日` | 12-hour and Chinese forms |
| `2024-03-01T13:03:15Z`, `…+08:00` | converted to the import timezone |
| `1709298195`, `1709298195000` (seconds / ms / µs / ns) | converted to the import timezone |
| `17/04/2023 20:30`, `4/17/23, 8:30 PM` | day/month order inferred; truly ambiguous values (`03/04/2024` everywhere) are reported, never guessed |

The import timezone is this computer's local zone unless you pass `--timezone Asia/Shanghai` (or `UTC+8`).

## Encodings

UTF-8 (with or without BOM) and GB18030/GBK are detected automatically.

## Media files

Put them in any folder structure and pass the folder(s) to `--media`.

| kind | extensions | notes |
| --- | --- | --- |
| photos | jpg jpeg png webp gif bmp | EXIF date and orientation honoured; HEIC/HEIF detected but reported as unsupported |
| voice / audio | mp3 wav m4a aac ogg opus flac amr wma caf silk | files named `voice…`, `PTT-…`, `录音…`, inside a `voice`/`语音` folder, or `.amr/.silk/.opus` are treated as voice messages; `.amr/.wma/.caf` get a browser-playable `.m4a` copy when ffmpeg is available; `.silk` is not decodable |
| video | mp4 mov m4v 3gp webm mkv avi | duration, resolution, rotation, creation time, poster frame |

Capture-time sources, best first: EXIF `DateTimeOriginal` → video metadata (`com.apple.quicktime.creationdate`, `creation_time`) → filename (`IMG_20230417_203015`, `VID_…`, `PXL_20230417_203015123`, `Screenshot 2023-04-17 at 20.30.15`, `IMG-20230417-WA0001` (date only), `mmexport1681734615000`) → file modification time (flagged as possibly wrong). A linked chat message's send time replaces the last two.

## What the report tells you

`records_seen`, `imported`, `duplicates` skipped, per-type counts, and issue counts with up to 200 examples: `malformed`, `missing_timestamp`, `bad_timestamp`, `unknown_type`, `missing_sender`, `unreadable_file`, `unsupported_file`; for media: new/updated/unchanged, corrupt/unsupported files with the error, duplicates, files that disappeared, and where capture times came from; for linking: exact/high/medium/low counts, references that matched no file, media messages without any file. Save everything with `--report report.json`.
