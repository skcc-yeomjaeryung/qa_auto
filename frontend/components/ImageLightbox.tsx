"use client";

import { useCallback, useEffect } from "react";
import { AssistantGuide } from "./AssistantGuide";

export type LightboxImage = {
  src: string;
  caption?: string;
};

/**
 * 증적 스크린샷 확대 보기. 증적 갤러리·플로우 노드 캡쳐가 함께 쓴다.
 * Esc·배경 클릭으로 닫고, 여러 장이면 ←/→ 로 넘긴다.
 */
export function ImageLightbox({
  images,
  index,
  onClose,
  onIndexChange,
}: {
  images: LightboxImage[];
  index: number;
  onClose: () => void;
  onIndexChange?: (next: number) => void;
}) {
  const total = images.length;
  const move = useCallback(
    (delta: number) => {
      if (!onIndexChange || total < 2) return;
      onIndexChange((index + delta + total) % total);
    },
    [index, total, onIndexChange]
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") move(1);
      if (e.key === "ArrowLeft") move(-1);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose, move]);

  const current = images[index];
  if (!current) return null;

  return (
    <div
      className="img-lightbox anim-fade-in"
      role="dialog"
      aria-modal="true"
      aria-label="증적 스크린샷 확대"
      data-testid="image-lightbox"
      onClick={onClose}
    >
      <div className="img-lightbox-body" onClick={(e) => e.stopPropagation()}>
        <div className="img-lightbox-head">
          <span className="img-lightbox-caption">{current.caption || "스크린샷"}</span>
          <span className="muted">
            {total > 1 ? `${index + 1} / ${total}` : ""}
          </span>
          <button
            type="button"
            className="ghost-btn"
            onClick={onClose}
            data-testid="lightbox-close"
            aria-label="확대 보기 닫기"
          >
            닫기
          </button>
        </div>
        <AssistantGuide compact title="이 화면이 실행 증적이에요" message="캡처 시점과 단계 설명을 함께 확인해 관측 결과를 검토할 수 있습니다." />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={current.src} alt={current.caption || "증적 스크린샷"} />
        {total > 1 && (
          <div className="img-lightbox-nav">
            <button type="button" className="ghost-btn" onClick={() => move(-1)} aria-label="이전 스크린샷">
              ← 이전
            </button>
            <button type="button" className="ghost-btn" onClick={() => move(1)} aria-label="다음 스크린샷">
              다음 →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
