"use client";

export type CommonDialogTab = {
  id: string;
  label: string;
  count?: number;
};

/** 팝업·드로어가 긴 단일 스크롤이 되지 않도록 내용을 공통 탭으로 나눈다. */
export function CommonDialogTabs({
  tabs,
  value,
  onChange,
  label = "상세 정보 보기",
}: {
  tabs: CommonDialogTab[];
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  return (
    <div className="common-dialog-tabs" role="tablist" aria-label={label}>
      {tabs.map((tab) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={selected}
            className={selected ? "is-active" : ""}
            onClick={() => onChange(tab.id)}
          >
            <span>{tab.label}</span>
            {tab.count !== undefined && <em>{tab.count}</em>}
          </button>
        );
      })}
    </div>
  );
}
