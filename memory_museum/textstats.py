"""Explainable word / emoji frequency counting with Chinese support.

Uses ``jieba`` for Chinese word segmentation when installed. Without it, a
simple fallback counts 2-character Chinese sequences (bigrams), which is
cruder — the UI labels which method was used.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

try:  # optional dependency
    import jieba  # type: ignore

    jieba.setLogLevel(60)
    HAVE_JIEBA = True
except Exception:  # pragma: no cover - depends on environment
    jieba = None
    HAVE_JIEBA = False

STOP_ZH = set("""
的 了 我 你 他 她 它 们 是 在 吗 呢 吧 啊 呀 哦 噢 嗯 恩 哈 也 就 都 和 与 跟 不 没 这 那 有 个 一 很 还 要 去 会 说 到 着 过
把 被 给 让 从 对 为 而 但 所以 因为 然后 就是 还是 可以 什么 怎么 这个 那个 这样 那样 我们 你们 他们 她们 自己 一个 一下 已经
现在 今天 明天 昨天 时候 没有 不是 知道 觉得 感觉 一样 一点 有点 真的 应该 可能 如果 或者 还有 这么 那么 然后 其实 只是 只有
而且 就会 之后 之前 以后 以前 起来 出来 下来 上来 过来 回来 不会 不要 不能 不过 的话 啊啊 哦哦 嗯嗯 好的 好吧 是的 对的 对啊
一直 一起 这些 那些 哪里 这里 那里 为什么 怎么样 多少 几个 还没 要不 要是 这边 那边 这种 那种 东西 事情 地方 问题
""".split())

STOP_EN = set("""
a an the and or but if of to in on at for with is are was were be been am i you he she it we they me my your our
his her its them this that these those do did does have has had not no so just too very can could will would
should what when where who how why yes ok okay oh lol im its dont thats u ur
""".split())

_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_MARKER = re.compile(r"[\[【<][^\]】>]{1,12}[\]】>]")
_CJK = re.compile(r"[一-鿿]+")
_LATIN = re.compile(r"[A-Za-z][A-Za-z']{1,}")
_EMOJI_CHAR = ("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F\U0001F0A0-\U0001F0FF❤♥]"
               "[️\U0001F3FB-\U0001F3FF]?")
# ZWJ sequences such as 😮‍💨 count as one emoji
_EMOJI = re.compile(f"{_EMOJI_CHAR}(?:‍{_EMOJI_CHAR})*")


def clean(text: str) -> str:
    return _MARKER.sub(" ", _URL.sub(" ", text))


def tokenize(text: str, use_jieba: bool | None = None) -> list[str]:
    use_jieba = HAVE_JIEBA if use_jieba is None else (use_jieba and HAVE_JIEBA)
    text = clean(text)
    words: list[str] = []
    for w in _LATIN.findall(text):
        lw = w.lower().strip("'")
        if len(lw) >= 2 and lw not in STOP_EN:
            words.append(lw)
    for run in _CJK.findall(text):
        if use_jieba:
            parts = jieba.lcut(run)
        else:
            parts = [run[i:i + 2] for i in range(len(run) - 1)] if len(run) >= 2 else []
        for p in parts:
            if len(p) >= 2 and p not in STOP_ZH and not re.fullmatch(r"(.)\1+", p):
                words.append(p)
    return words


def emojis(text: str) -> list[str]:
    return _EMOJI.findall(text)


def count_words(texts: Iterable[str], top: int = 40) -> dict:
    words: Counter[str] = Counter()
    emo: Counter[str] = Counter()
    laughs = 0
    for t in texts:
        if not t:
            continue
        words.update(tokenize(t))
        emo.update(emojis(t))
        if re.search(r"哈{2,}|hhh+|haha", t, re.IGNORECASE):
            laughs += 1
    return {
        "method": "jieba" if HAVE_JIEBA else "bigram",
        "words": words.most_common(top),
        "emojis": emo.most_common(12),
        "laugh_messages": laughs,
    }
