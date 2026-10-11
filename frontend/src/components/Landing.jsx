export default function Landing() {
  return (
    <div>
      <section className="hero">
        <h1>
          Lost something <em>on campus?</em>
        </h1>
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
