import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Empty, ErrorBox, Loading, PageHeader } from "../components/common";
import { IconSearch } from "../components/Icons";
import { api } from "../lib/api";
import { formatDay, formatTime } from "../lib/format";
import { useInfinite } from "../lib/hooks";
import { useApp } from "../lib/store";
import type { Message } from "../lib/types";

function Highlight({ text, q }: { text: string; q: string }) {
  if (!q) return <>{text}</>;
  const parts = text.split(q);
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {i < parts.length - 1 && <mark>{q}</mark>}
        </span>
      ))}
    </>
  );
}

export default function Search() {
  const { t, lang, nameOf, settings } = useApp();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [input, setInput] = useState(q);

  useEffect(() => {
    const id = window.setTimeout(() => {
      if (input.trim() !== q) setParams(input.trim() ? { q: input.trim() } : {}, { replace: true });
    }, 300);
    return () => window.clearTimeout(id);
  }, [input, q, setParams]);

  const list = useInfinite<Message>((cursor) => (q ? api.search(q, cursor) : Promise.resolve({ items: [], next_cursor: null })), [q]);

  return (
    <div className="page">
      <PageHeader title={t("home.search")} />
      <div className="search-box" style={{ marginBottom: 20 }}>
        <IconSearch />
        <input className="input" type="search" autoFocus value={input} placeholder={t("search.placeholder")}
          aria-label={t("search.placeholder")} onChange={(e) => setInput(e.target.value)} />
      </div>
      {list.error && <ErrorBox error={list.error} />}
      {q && !list.loading && list.items.length === 0 && <Empty glyph="寻">{t("search.empty")}</Empty>}
      {list.items.map((m) => (
        <Link key={m.id} to={`/day/${m.day}`} className="list-link" style={{ alignItems: "flex-start" }}>
          <div className="grow">
            <div className="tiny muted">
              {m.day && formatDay(m.day, lang, settings?.date_format)} {formatTime(m.ts)} · {nameOf(m.sender_id)}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}><Highlight text={m.text ?? ""} q={q} /></div>
          </div>
        </Link>
      ))}
      <div ref={list.sentinel} />
      {list.loading && q && <Loading />}
    </div>
  );
}
