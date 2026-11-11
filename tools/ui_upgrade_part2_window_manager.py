#!/usr/bin/env python3
"""
ui_upgrade_part2_window_manager.py — Part 2 of 3
================================================
Senior Payment Architect UI Upgrade for RAJON Private Host Simulator:
  1. Multi-Window & Split-Screen Workspace State (`frontend/src/workspace/WorkspaceContext.tsx`):
     - Manages Floating Pop-out Windows (open, focus/bring-to-front, resize presets S/M/L/XL/MAX,
       free-form drag & corner/edge resize, minimize to dock, promote to main canvas, or dock
       side-by-side).
     - Manages Side-by-Side Split-Screen View so you can keep Transaction Simulator on the left
       and Live Execution Monitor / Transaction Log Viewer / HSM Workbench on the right.
     - Supports `Default Navigation Mode`:
       * "POPOUT_MODE": Clicking any sidebar sub-module automatically pops it out as a floating
         resizable window while keeping your current main screen untouched!
       * "MAIN_MODE": Standard main-view navigation (with one-click Pop-Out and Split-View action
         buttons on every item).
  2. Interactive Floating Window Manager (`frontend/src/workspace/FloatingWindowManager.tsx`):
     - Smooth drag-and-drop title bar, 8-direction resize handles, quick size pills (`S`, `M`,
       `L`, `XL`, `MAX`), minimize-to-tray, dock-to-split, swap-to-main, and global `ESC` key
       listener to close the top active pop-out window (or close split view).

Run from project root (or tools/ directory):
    python ui_upgrade_part2_window_manager.py
"""

from datetime import datetime
from pathlib import Path
import shutil


def resolve_project_root() -> Path:
    here = Path(__file__).resolve().parent
    if (here / "frontend" / "src").exists():
        return here
    if (here.parent / "frontend" / "src").exists():
        return here.parent
    cwd = Path.cwd()
    if (cwd / "frontend" / "src").exists():
        return cwd
    raise RuntimeError("Could not locate 'frontend/src'. Please run this script from the project root folder.")


PROJECT_ROOT = resolve_project_root()
BACKUP_ROOT = PROJECT_ROOT / "_backups" / f"ui_upgrade_p2_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def write_project_file(rel_path: str, content: str) -> None:
    target = PROJECT_ROOT / rel_path
    if target.exists():
        bkp = BACKUP_ROOT / rel_path
        bkp.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, bkp)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  [OK] Wrote {rel_path} ({len(content):,} bytes)")


WORKSPACE_CONTEXT_TSX = r"""import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
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
"""


FLOATING_WINDOW_MANAGER_TSX = r"""import React, { useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  X,
  Minus,
  Maximize2,
  Minimize2,
  Columns,
  ArrowUpRight,
  GripHorizontal,
  Layers,
  Trash2,
} from 'lucide-react';
import {
  useWorkspace,
  FloatingWindowInstance,
  WindowSizePreset,
} from './WorkspaceContext';
import { IsolatedRouteViewport } from './RouteRenderer';
import { resolveNavMeta } from './navRegistry';

const SIZE_PRESETS: { key: WindowSizePreset; label: string; tip: string }[] = [
  { key: 'SM', label: 'S', tip: 'Compact Window (48%)' },
  { key: 'MD', label: 'M', tip: 'Medium Window (65%)' },
  { key: 'LG', label: 'L', tip: 'Large Workbench (78%)' },
  { key: 'XL', label: 'XL', tip: 'Extra Large (90%)' },
  { key: 'MAX', label: 'MAX', tip: 'Full Viewport' },
];

const SingleFloatingWindow: React.FC<{
  win: FloatingWindowInstance;
  isActive: boolean;
}> = ({ win, isActive }) => {
  const {
    focusWindow,
    closePopoutWindow,
    toggleMinimizeWindow,
    setWindowSizePreset,
    updateWindowGeometry,
    openSideBySideSplit,
  } = useWorkspace();
  const navigate = useNavigate();
  const meta = resolveNavMeta(win.path);
  const Icon = meta.icon;

  const [dragging, setDragging] = useState(false);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    origX: number;
    origY: number;
  } | null>(null);

  const handleHeaderMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return;
    focusWindow(win.id);
    if (win.sizePreset === 'MAX') return;

    setDragging(true);
    dragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      origX: win.x,
      origY: win.y,
    };

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.startX;
      const dy = ev.clientY - dragRef.current.startY;
      const nextX = Math.max(8, Math.min(window.innerWidth - 180, dragRef.current.origX + dx));
      const nextY = Math.max(44, Math.min(window.innerHeight - 80, dragRef.current.origY + dy));
      updateWindowGeometry(win.id, { x: nextX, y: nextY });
    };

    const onUp = () => {
      setDragging(false);
      dragRef.current = null;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const handleResizeMouseDown = (
    e: React.MouseEvent,
    direction: 'se' | 'e' | 's' | 'sw' | 'w'
  ) => {
    e.stopPropagation();
    e.preventDefault();
    focusWindow(win.id);

    const startX = e.clientX;
    const startY = e.clientY;
    const origW = win.width;
    const origH = win.height;
    const origX = win.x;

    const onMove = (ev: MouseEvent) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      const patch: Partial<Pick<FloatingWindowInstance, 'x' | 'y' | 'width' | 'height'>> = {};

      if (direction.includes('e')) {
        patch.width = Math.max(440, Math.min(window.innerWidth - origX - 12, origW + dx));
      }
      if (direction.includes('s')) {
        patch.height = Math.max(320, Math.min(window.innerHeight - win.y - 12, origH + dy));
      }
      if (direction.includes('w')) {
        const newWidth = Math.max(440, origW - dx);
        const shiftX = origW - newWidth;
        patch.width = newWidth;
        patch.x = Math.max(8, origX + shiftX);
      }
      updateWindowGeometry(win.id, patch);
    };

    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  if (win.minimized) return null;

  return (
    <div
      onMouseDown={() => focusWindow(win.id)}
      style={{
        left: `${win.x}px`,
        top: `${win.y}px`,
        width: `${win.width}px`,
        height: `${win.height}px`,
        zIndex: win.zIndex,
      }}
      className={`fixed flex flex-col rounded-2xl overflow-hidden transition-shadow duration-150 ${
        isActive
          ? 'ring-2 ring-emerald-500/80 shadow-[0_25px_70px_-15px_rgba(0,0,0,0.85)]'
          : 'ring-1 ring-slate-700/80 shadow-2xl opacity-95'
      } bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800`}
    >
      {/* Window Title Bar */}
      <div
        onMouseDown={handleHeaderMouseDown}
        onDoubleClick={() =>
          setWindowSizePreset(win.id, win.sizePreset === 'MAX' ? 'LG' : 'MAX')
        }
        className={`h-11 px-3.5 flex items-center justify-between select-none shrink-0 ${
          dragging ? 'cursor-grabbing' : 'cursor-grab'
        } ${
          isActive
            ? 'bg-gradient-to-r from-slate-900 via-slate-900 to-emerald-950/90 text-white border-b border-emerald-500/30'
            : 'bg-slate-900 text-slate-300 border-b border-slate-800'
        }`}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <GripHorizontal size={14} className="text-slate-500 shrink-0" />
          <div className="p-1.5 rounded-lg bg-slate-800/90 border border-slate-700/80">
            <Icon size={14} className={meta.accentColor} />
          </div>
          <span className="px-1.5 py-0.5 rounded bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-mono text-[10px] font-bold shrink-0">
            {win.code}
          </span>
          <div className="truncate">
            <span className="text-xs font-bold tracking-tight text-white">{win.title}</span>
            <span className="hidden md:inline text-[10px] font-mono text-slate-400 ml-2">
              [{win.branchTitle}]
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {/* Quick Size Preset Pills (S / M / L / XL / MAX) */}
          <div className="hidden sm:flex items-center bg-slate-950/80 border border-slate-800 rounded-lg p-0.5 mr-1">
            {SIZE_PRESETS.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setWindowSizePreset(win.id, p.key)}
                title={p.tip}
                className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-bold transition ${
                  win.sizePreset === p.key
                    ? 'bg-emerald-600 text-white shadow'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Dock to Side-by-Side Split View */}
          <button
            type="button"
            onClick={() => {
              openSideBySideSplit(win.path);
              closePopoutWindow(win.id);
            }}
            title="Dock Side-by-Side (Split Screen)"
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-sky-400 transition"
          >
            <Columns size={14} />
          </button>

          {/* Promote to Main Background Canvas */}
          <button
            type="button"
            onClick={() => {
              navigate(win.path);
              closePopoutWindow(win.id);
            }}
            title="Promote to Primary Canvas & Close Pop-out"
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-emerald-400 transition"
          >
            <ArrowUpRight size={14} />
          </button>

          {/* Minimize to Bottom Tray */}
          <button
            type="button"
            onClick={() => toggleMinimizeWindow(win.id)}
            title="Minimize to Workspace Dock"
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-amber-300 transition"
          >
            <Minus size={14} />
          </button>

          {/* Toggle Maximize */}
          <button
            type="button"
            onClick={() =>
              setWindowSizePreset(win.id, win.sizePreset === 'MAX' ? 'LG' : 'MAX')
            }
            title={win.sizePreset === 'MAX' ? 'Restore Size' : 'Maximize Window'}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition"
          >
            {win.sizePreset === 'MAX' ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>

          {/* Close Window (ESC) */}
          <button
            type="button"
            onClick={() => closePopoutWindow(win.id)}
            title="Close Window (Press ESC)"
            className="flex items-center gap-1 px-2 py-1 rounded-lg bg-rose-950/80 hover:bg-rose-600 text-rose-200 hover:text-white border border-rose-800/60 text-[10px] font-mono font-bold transition"
          >
            <X size={13} />
            <span className="hidden lg:inline">ESC</span>
          </button>
        </div>
      </div>

      {/* Window Content Body */}
      <div className="flex-1 overflow-y-auto p-5 bg-slate-100/90 dark:bg-slate-950">
        <IsolatedRouteViewport initialPath={win.path} />
      </div>

      {/* Window Footer Status Bar + Resize Grips */}
      <div className="h-6 px-3 bg-slate-900 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-400 select-none shrink-0">
        <div className="flex items-center gap-2 truncate">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
          <span>POP-OUT WORKBENCH: {win.path}</span>
          <span className="text-slate-600">|</span>
          <span className="text-slate-400">Drag header to move · Drag corners/edges to resize · Press ESC to close</span>
        </div>
        <div className="text-slate-500 shrink-0">
          {win.width} × {win.height}px
        </div>
      </div>

      {/* Resize Handles */}
      {win.sizePreset !== 'MAX' && (
        <>
          <div
            onMouseDown={(e) => handleResizeMouseDown(e, 'e')}
            className="absolute top-11 right-0 bottom-4 w-2 cursor-ew-resize hover:bg-emerald-500/30"
          />
          <div
            onMouseDown={(e) => handleResizeMouseDown(e, 'w')}
            className="absolute top-11 left-0 bottom-4 w-2 cursor-ew-resize hover:bg-emerald-500/30"
          />
          <div
            onMouseDown={(e) => handleResizeMouseDown(e, 's')}
            className="absolute bottom-0 left-4 right-4 h-2 cursor-ns-resize hover:bg-emerald-500/30"
          />
          <div
            onMouseDown={(e) => handleResizeMouseDown(e, 'se')}
            className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize bg-emerald-500/20 hover:bg-emerald-500/60 rounded-tl"
            title="Drag to resize window"
          />
          <div
            onMouseDown={(e) => handleResizeMouseDown(e, 'sw')}
            className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize bg-emerald-500/20 hover:bg-emerald-500/60 rounded-tr"
            title="Drag to resize window"
          />
        </>
      )}
    </div>
  );
};

export const FloatingWindowManager: React.FC = () => {
  const {
    windows,
    activeWindowId,
    focusWindow,
    closePopoutWindow,
    closeAllWindows,
  } = useWorkspace();

  if (windows.length === 0) return null;

  return (
    <>
      {windows.map((win) => (
        <SingleFloatingWindow
          key={win.id}
          win={win}
          isActive={win.id === activeWindowId}
        />
      ))}

      {/* Floating Bottom Taskbar Dock for Open / Minimized Pop-out Windows */}
      <div className="fixed bottom-3 right-4 z-[999] flex items-center gap-1.5 bg-slate-900/95 backdrop-blur-md border border-slate-700/90 rounded-xl px-2.5 py-1.5 shadow-2xl">
        <div className="flex items-center gap-1.5 px-2 py-1 text-[10px] font-mono font-bold text-emerald-400 border-r border-slate-800">
          <Layers size={13} />
          <span>WINDOWS ({windows.length})</span>
        </div>

        <div className="flex items-center gap-1.5 max-w-[60vw] overflow-x-auto">
          {windows.map((w) => {
            const isFocused = w.id === activeWindowId && !w.minimized;
            return (
              <div
                key={w.id}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono cursor-pointer transition border ${
                  isFocused
                    ? 'bg-emerald-600/90 text-white border-emerald-400 shadow-sm'
                    : w.minimized
                    ? 'bg-slate-800/70 text-amber-300 border-amber-500/30 hover:bg-slate-800'
                    : 'bg-slate-800 text-slate-200 border-slate-700 hover:bg-slate-700'
                }`}
                onClick={() => focusWindow(w.id)}
                title={`${w.title} — Click to focus/restore`}
              >
                <span className="text-[10px] opacity-75">{w.code}</span>
                <span className="truncate max-w-[130px] font-semibold">{w.shortLabel}</span>
                {w.minimized && (
                  <span className="text-[9px] px-1 rounded bg-amber-500/20 text-amber-300">
                    MIN
                  </span>
                )}
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    closePopoutWindow(w.id);
                  }}
                  className="hover:text-rose-300 ml-0.5"
                  title="Close window"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
        </div>

        <button
          type="button"
          onClick={closeAllWindows}
          title="Close all pop-out windows"
          className="p-1.5 rounded-lg hover:bg-rose-950 text-slate-400 hover:text-rose-300 border border-transparent hover:border-rose-800/50 transition ml-1"
        >
          <Trash2 size={13} />
        </button>
      </div>
    </>
  );
};
"""


def main() -> None:
    print("=" * 76)
    print("RAJON HOST UI UPGRADE (PART 2/3) — Multi-Window & Split-Screen Manager")
    print("=" * 76)
    write_project_file("frontend/src/workspace/WorkspaceContext.tsx", WORKSPACE_CONTEXT_TSX)
    write_project_file("frontend/src/workspace/FloatingWindowManager.tsx", FLOATING_WINDOW_MANAGER_TSX)
    print("-" * 76)
    print("Part 2 complete! Next, run: python ui_upgrade_part3_architect_layout.py")


if __name__ == "__main__":
    main()
