import React, { useRef, useState } from 'react';
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
