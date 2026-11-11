import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { resolveNavMeta } from './navRegistry';

export type WindowSizePreset = 'SM' | 'MD' | 'LG' | 'XL' | 'MAX';
export type SubTreeDisplayMode = 'ACCORDION' | 'SIDE_FLYOUT';
export type ClickBehaviorMode = 'POPOUT' | 'MAIN_CANVAS';

export interface FloatingWindowInstance {
  id: string;
  path: string;
  title: string;
  shortLabel: string;
  code: string;
  branchTitle: string;
  sizePreset: WindowSizePreset;
  minimized: boolean;
  zIndex: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface WorkspaceContextValue {
  windows: FloatingWindowInstance[];
  activeWindowId: string | null;
  splitPath: string | null;
  splitWidthPercent: number;
  subTreeMode: SubTreeDisplayMode;
  clickBehavior: ClickBehaviorMode;
  commandPaletteOpen: boolean;
  setSubTreeMode: (mode: SubTreeDisplayMode) => void;
  setClickBehavior: (mode: ClickBehaviorMode) => void;
  setCommandPaletteOpen: (open: boolean) => void;
  setSplitWidthPercent: (pct: number) => void;
  openPopoutWindow: (path: string, preset?: WindowSizePreset) => void;
  closePopoutWindow: (id: string) => void;
  closeTopmostWindow: () => boolean;
  closeAllWindows: () => void;
  focusWindow: (id: string) => void;
  toggleMinimizeWindow: (id: string) => void;
  setWindowSizePreset: (id: string, preset: WindowSizePreset) => void;
  updateWindowGeometry: (id: string, geom: Partial<Pick<FloatingWindowInstance, 'x' | 'y' | 'width' | 'height'>>) => void;
  openSideBySideSplit: (path: string) => void;
  closeSideBySideSplit: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | undefined>(undefined);

function computePresetDimensions(preset: WindowSizePreset, indexOffset = 0): {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  const vw = typeof window !== 'undefined' ? window.innerWidth : 1440;
  const vh = typeof window !== 'undefined' ? window.innerHeight : 900;

  const cascade = (indexOffset % 5) * 26;

  if (preset === 'SM') {
    const width = Math.min(720, Math.round(vw * 0.48));
    const height = Math.min(540, Math.round(vh * 0.58));
    return {
      width,
      height,
      x: Math.max(40, Math.round((vw - width) / 2) + cascade),
      y: Math.max(56, Math.round((vh - height) / 2) + cascade),
    };
  }
  if (preset === 'MD') {
    const width = Math.min(980, Math.round(vw * 0.65));
    const height = Math.min(680, Math.round(vh * 0.72));
    return {
      width,
      height,
      x: Math.max(36, Math.round((vw - width) / 2) + cascade),
      y: Math.max(52, Math.round((vh - height) / 2) + cascade),
    };
  }
  if (preset === 'XL') {
    const width = Math.round(vw * 0.90);
    const height = Math.round(vh * 0.88);
    return {
      width,
      height,
      x: Math.max(16, Math.round((vw - width) / 2)),
      y: Math.max(44, Math.round((vh - height) / 2)),
    };
  }
  if (preset === 'MAX') {
    return {
      width: vw - 24,
      height: vh - 64,
      x: 12,
      y: 52,
    };
  }
  // Default 'LG'
  const width = Math.min(1220, Math.round(vw * 0.78));
  const height = Math.min(790, Math.round(vh * 0.82));
  return {
    width,
    height,
    x: Math.max(28, Math.round((vw - width) / 2) + cascade),
    y: Math.max(48, Math.round((vh - height) / 2) + cascade),
  };
}

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [windows, setWindows] = useState<FloatingWindowInstance[]>([]);
  const [activeWindowId, setActiveWindowId] = useState<string | null>(null);
  const [splitPath, setSplitPath] = useState<string | null>(null);
  const [splitWidthPercent, setSplitWidthPercent] = useState<number>(48);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState<boolean>(false);

  const [subTreeMode, setSubTreeModeState] = useState<SubTreeDisplayMode>(() => {
    const saved = localStorage.getItem('RAJON_SUBTREE_MODE');
    return saved === 'ACCORDION' || saved === 'SIDE_FLYOUT' ? saved : 'SIDE_FLYOUT';
  });

  const [clickBehavior, setClickBehaviorState] = useState<ClickBehaviorMode>(() => {
    const saved = localStorage.getItem('RAJON_CLICK_BEHAVIOR');
    return saved === 'POPOUT' || saved === 'MAIN_CANVAS' ? saved : 'POPOUT';
  });

  const setSubTreeMode = useCallback((mode: SubTreeDisplayMode) => {
    setSubTreeModeState(mode);
    localStorage.setItem('RAJON_SUBTREE_MODE', mode);
  }, []);

  const setClickBehavior = useCallback((mode: ClickBehaviorMode) => {
    setClickBehaviorState(mode);
    localStorage.setItem('RAJON_CLICK_BEHAVIOR', mode);
  }, []);

  const openPopoutWindow = useCallback((path: string, preset: WindowSizePreset = 'LG') => {
    const meta = resolveNavMeta(path);
    setWindows((prev) => {
      const maxZ = prev.reduce((m, w) => Math.max(m, w.zIndex), 100);
      const existing = prev.find((w) => w.path === path);
      if (existing) {
        setActiveWindowId(existing.id);
        return prev.map((w) =>
          w.id === existing.id
            ? { ...w, minimized: false, zIndex: maxZ + 1 }
            : w
        );
      }
      const dims = computePresetDimensions(preset, prev.length);
      const newWin: FloatingWindowInstance = {
        id: `win-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        path,
        title: meta.label,
        shortLabel: meta.shortLabel,
        code: meta.code,
        branchTitle: meta.branchTitle,
        sizePreset: preset,
        minimized: false,
        zIndex: maxZ + 1,
        ...dims,
      };
      setActiveWindowId(newWin.id);
      return [...prev, newWin];
    });
  }, []);

  const closePopoutWindow = useCallback((id: string) => {
    setWindows((prev) => {
      const next = prev.filter((w) => w.id !== id);
      if (next.length === 0) {
        setActiveWindowId(null);
      } else {
        const top = [...next].sort((a, b) => b.zIndex - a.zIndex)[0];
        setActiveWindowId(top ? top.id : null);
      }
      return next;
    });
  }, []);

  const closeTopmostWindow = useCallback((): boolean => {
    if (commandPaletteOpen) {
      setCommandPaletteOpen(false);
      return true;
    }
    const visibleWins = windows.filter((w) => !w.minimized);
    if (visibleWins.length > 0) {
      const top = [...visibleWins].sort((a, b) => b.zIndex - a.zIndex)[0];
      closePopoutWindow(top.id);
      return true;
    }
    if (splitPath) {
      setSplitPath(null);
      return true;
    }
    return false;
  }, [commandPaletteOpen, windows, splitPath, closePopoutWindow]);

  const closeAllWindows = useCallback(() => {
    setWindows([]);
    setActiveWindowId(null);
  }, []);

  const focusWindow = useCallback((id: string) => {
    setActiveWindowId(id);
    setWindows((prev) => {
      const maxZ = prev.reduce((m, w) => Math.max(m, w.zIndex), 100);
      return prev.map((w) =>
        w.id === id ? { ...w, minimized: false, zIndex: maxZ + 1 } : w
      );
    });
  }, []);

  const toggleMinimizeWindow = useCallback((id: string) => {
    setWindows((prev) =>
      prev.map((w) => (w.id === id ? { ...w, minimized: !w.minimized } : w))
    );
  }, []);

  const setWindowSizePreset = useCallback((id: string, preset: WindowSizePreset) => {
    setWindows((prev) => {
      const maxZ = prev.reduce((m, w) => Math.max(m, w.zIndex), 100);
      return prev.map((w, idx) => {
        if (w.id !== id) return w;
        const dims = computePresetDimensions(preset, idx);
        return {
          ...w,
          sizePreset: preset,
          minimized: false,
          zIndex: maxZ + 1,
          ...dims,
        };
      });
    });
  }, []);

  const updateWindowGeometry = useCallback(
    (id: string, geom: Partial<Pick<FloatingWindowInstance, 'x' | 'y' | 'width' | 'height'>>) => {
      setWindows((prev) =>
        prev.map((w) => (w.id === id ? { ...w, ...geom } : w))
      );
    },
    []
  );

  const openSideBySideSplit = useCallback((path: string) => {
    setSplitPath(path);
  }, []);

  const closeSideBySideSplit = useCallback(() => {
    setSplitPath(null);
  }, []);

  // Global keyboard shortcuts:
  // - ESC closes topmost pop-out window (or command palette / split view)
  // - Ctrl+K / Cmd+K opens quick architect command launcher
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
        return;
      }
      if (e.key === 'Escape') {
        const tag = (e.target as HTMLElement)?.tagName || '';
        // If user is typing inside an input/textarea/select, blur it first; second ESC closes window
        if (['INPUT', 'TEXTAREA', 'SELECT'].includes(tag)) {
          (e.target as HTMLElement).blur();
          return;
        }
        const handled = closeTopmostWindow();
        if (handled) {
          e.preventDefault();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeTopmostWindow]);

  return (
    <WorkspaceContext.Provider
      value={{
        windows,
        activeWindowId,
        splitPath,
        splitWidthPercent,
        subTreeMode,
        clickBehavior,
        commandPaletteOpen,
        setSubTreeMode,
        setClickBehavior,
        setCommandPaletteOpen,
        setSplitWidthPercent,
        openPopoutWindow,
        closePopoutWindow,
        closeTopmostWindow,
        closeAllWindows,
        focusWindow,
        toggleMinimizeWindow,
        setWindowSizePreset,
        updateWindowGeometry,
        openSideBySideSplit,
        closeSideBySideSplit,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
};

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used inside a WorkspaceProvider');
  }
  return ctx;
}
