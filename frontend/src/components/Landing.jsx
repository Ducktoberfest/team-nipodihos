export default function Landing({ onReport, onBrowse }) {
  return (
    <div>
      <section className="hero">
        <span className="eyebrow">Team Nipodihos · Ducktoberfest Baku 2026</span>
        <h1>
          Lost something <em>on campus?</em>
        </h1>
        <p className="lede">
          FoundIt compares your description with items other people have handed
          in — even when they describe the same thing in completely different
          words. For every suggestion it shows you the evidence for and against,
          so you decide whether it is worth following up.
        </p>
        <div className="btn-group">
          <button className="btn" onClick={() => onReport("lost")}>
            I lost something
          </button>
          <button className="btn secondary" onClick={() => onReport("found")}>
            I found something
          </button>
          <button className="btn secondary" onClick={onBrowse}>
            Browse reports
          </button>
        </div>
      </section>

      <section className="steps">
        <div className="step">
          <span className="num">1</span>
          <h3>Describe it</h3>
          <p>
            Plain words are fine. Add a private detail only the real owner would
            know — it is never shown to anyone.
          </p>
        </div>
        <div className="step">
          <span className="num">2</span>
          <h3>The AI compares</h3>
          <p>
            It reads reports of the opposite type and recognises synonyms:
            "navy school bag" and "dark blue backpack" are the same item.
          </p>
        </div>
        <div className="step">
          <span className="num">3</span>
          <h3>Verify and recover</h3>
          <p>
            Every suggestion comes with matching and conflicting evidence, plus
            a clear next step before any handover.
          </p>
        </div>
      </section>
    </div>
  );
}
