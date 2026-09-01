# Windows QTreeView setIconSize Crash — Known Qt/GDI Bug

## Problem

On Windows, setting `setIconSize(QSize(128, 128))` on a `QTreeView` (with shared `QFileSystemModel`) causes an **immediate C++-level segfault** when rendering large icons. Python exception handlers (`sys.excepthook`, `faulthandler`) CANNOT catch this — the process dies silently with no log.

Error from Windows Event Viewer (Application Error):
```
Exception code: 0xc0000005 (Access violation)
Faulting module: qwindows.dll
```

## Why It Happens

Qt on Windows uses GDI/GDI+ for icon rendering. Large icon sizes (≥128px) combined with the Windows system image list can trigger access violations in the native `qwindows.dll` platform plugin. This is a Qt bug, not a Python bug.

## Solution

**DO NOT use large icon sizes on Windows.** Safe sizes:
- `QSize(48, 48)` — safe
- `QSize(64, 64)` — usually safe
- `QSize(128, 128)` — CRASHES on Windows
- `QSize(16, 16)` — safe

For "extra large icon mode" functionality, you would need:
- A `QListView` with `setViewMode(QListView.IconMode)` (QListView has true icon mode; QTreeView does not)
- OR implement a custom `QStyledItemDelegate` with QPixmap thumbnails (but this has its own crash risks)
- OR use `QListWidget` for thumbnail views

## What Didn't Help

These were tried and failed to prevent the crash:
1. `sys.excepthook` — catches Python exceptions, NOT C++ segfaults
2. `faulthandler.enable()` — too late; segfault kills process before faulthandler writes
3. `ThumbnailDelegate` — custom delegate to safely load pixmaps; still crashes in Qt icon pipeline
4. Adding `try/except` around `setIconSize()` — crash happens asynchronously during paint, not at the call site

## Safe Pattern

```python
# Only two modes: icon (48px) and list (16px)
if mode == 'icon':
    self.tree_view.setIconSize(QSize(48, 48))
elif mode == 'list':
    self.tree_view.setIconSize(QSize(16, 16))
```

## User Impact

- User clicks "查看 mode" button → app crashes immediately
- No `pan4dex_crash.log` generated (crash is below Python)
- User has no idea why; must check Windows Event Viewer
- Recovery requires removing the problematic icon size

## Workaround for Thumbnail Preview

If image preview is required:
1. Use a separate `QListView` widget (NOT QTreeView) for thumbnail display
2. Load thumbnails in a background thread using `QPixmap.scaled(128, 128)` — but this is risky on Windows
3. Accept that image preview is not available on Windows with QTreeView

## Related Pitfall: Pyright Reports Valid PyQt6 API as Error

Pyright flags `setIconSize`, `standardIcon`, `IconMode` as "Cannot access attribute" on QTreeView because PyQt6 stubs are incomplete. **These are false positives from stub gaps.** The code works at runtime (except for the actual icon size crash). Don't silence Pyright — just be aware.
