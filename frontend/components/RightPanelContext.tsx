"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type RightPanelContextValue = {
  panel: ReactNode | null;
  setPanel: (node: ReactNode | null) => void;
  collapsed: boolean;
  setCollapsed: (value: boolean) => void;
  toggleCollapsed: () => void;
};

const STORAGE_KEY = "qa-auto.right-panel.collapsed";

const RightPanelContext = createContext<RightPanelContextValue | null>(null);

export function RightPanelProvider({ children }: { children: ReactNode }) {
  const [panel, setPanel] = useState<ReactNode | null>(null);
  const [collapsed, setCollapsedState] = useState(true);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "0") setCollapsedState(false);
      else if (saved === "1") setCollapsedState(true);
      // no key / unknown → keep default collapsed
    } catch {
      /* ignore */
    }
  }, []);

  const setCollapsed = useCallback((value: boolean) => {
    setCollapsedState(value);
    try {
      localStorage.setItem(STORAGE_KEY, value ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsedState((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({ panel, setPanel, collapsed, setCollapsed, toggleCollapsed }),
    [panel, collapsed, setCollapsed, toggleCollapsed],
  );

  return (
    <RightPanelContext.Provider value={value}>{children}</RightPanelContext.Provider>
  );
}

export function useRightPanel() {
  const ctx = useContext(RightPanelContext);
  if (!ctx) {
    throw new Error("useRightPanel must be used within RightPanelProvider");
  }
  return ctx;
}
