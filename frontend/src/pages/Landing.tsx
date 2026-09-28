import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { usePrefersReducedMotion } from "../lib/hooks";
import { useApp } from "../lib/store";

export default function Landing() {
  const { copy } = useApp();
  const navigate = useNavigate();
  const reduced = usePrefersReducedMotion();
  const [leaving, setLeaving] = useState(false);

  const enter = () => {
    if (reduced) return navigate("/home");
    setLeaving(true);
    window.setTimeout(() => navigate("/home"), 550);
  };

  if (!copy) return <div className="landing" />;
  const lines = copy.introLines ?? [];
  return (
    <div className={`landing ${leaving ? "leaving" : ""}`}>
      <div className="en">{copy.museumSubtitleEn}</div>
      <h1>{copy.museumTitle}</h1>
      <p className="intro">
        {lines.map((l, i) => (
          <span key={i} style={{ animationDelay: `${0.7 + i * 0.35}s` }}>
            {l}
          </span>
        ))}
      </p>
      <button className="btn primary enter" onClick={enter}>
        {copy.enterButton}
      </button>
      <div className="foot">{copy.footer}</div>
    </div>
  );
}
