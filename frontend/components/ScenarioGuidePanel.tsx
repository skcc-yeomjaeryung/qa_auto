"use client";

import type { ScenarioGuide } from "../lib/scenarioGuide";

/** 시나리오 상세 상단 안내 — 무엇을·어떻게·성공·실패·증적을 한글로 알려준다 */
export function ScenarioGuidePanel({ guide }: { guide: ScenarioGuide }) {
  return (
    <section className="scenario-guide anim-fade-in" data-testid="scenario-guide">
      <header className="scenario-guide-head">
        <span className="scenario-guide-kind">{guide.kindLabel}</span>
        <h3>{guide.headline}</h3>
        <p className="scenario-guide-purpose">{guide.purpose}</p>
      </header>

      <div className="scenario-guide-grid">
        <article className="scenario-guide-card">
          <h4>이 테스트가 하는 일</h4>
          <ol className="scenario-guide-steps">
            {guide.whatWeDo.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
        </article>

        <article className="scenario-guide-card">
          <h4>결과를 읽는 방법</h4>
          <dl className="scenario-guide-outcome">
            <div className="is-pass">
              <dt>성공으로 보이면</dt>
              <dd>{guide.successLooksLike}</dd>
            </div>
            <div className="is-fail">
              <dt>실패로 보이면</dt>
              <dd>{guide.failureLooksLike}</dd>
            </div>
            <div className="is-evidence">
              <dt>남는 증적</dt>
              <dd>{guide.evidenceNote}</dd>
            </div>
          </dl>
        </article>
      </div>

      {guide.cautions.length > 0 && (
        <ul className="scenario-guide-cautions">
          {guide.cautions.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
