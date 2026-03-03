from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable
from urllib.parse import quote
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageTk, UnidentifiedImageError
except ImportError:  # pragma: no cover - runtime fallback when Pillow is absent
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[assignment]

TreeProgressCallback = Callable[[int, int, str], None]


@dataclass
class ResourceEntry:
    logical_path: str
    physical_path: str
    hash_value: str
    offset: int
    size: int


@dataclass
class LoadedIndexes:
    tq_paths: list[str]
    res_paths: list[str]
    resource_map: dict[str, ResourceEntry]


class Toolbar(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_open_clicked: Callable[[], None],
        on_path_entered: Callable[[str], None],
    ) -> None:
        super().__init__(master, padding=(8, 8, 8, 4))
        self.path_var = tk.StringVar()

        self.columnconfigure(0, weight=1)

        self.path_entry = ttk.Entry(self, textvariable=self.path_var)
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.path_entry.bind(
            "<Return>", lambda _event: on_path_entered(self.path_var.get().strip())
        )

        self.open_button = ttk.Button(self, text="📂 Open", command=on_open_clicked)
        self.open_button.grid(row=0, column=1, sticky="e")

    def set_path(self, path: str) -> None:
        self.path_var.set(path)

    def get_path(self) -> str:
        return self.path_var.get().strip()


class StatusBar(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(8, 4))
        self.columnconfigure(0, weight=1)

        self.label = ttk.Label(self, anchor="w")
        self.label.grid(row=0, column=0, sticky="ew")

        self.progress = ttk.Progressbar(self, orient="horizontal", mode="determinate", length=220)
        self.progress.grid(row=0, column=1, sticky="e", padx=(8, 0))
        self.progress.configure(maximum=1, value=0)

    def set_text(self, text: str) -> None:
        self.label.config(text=text)

    def set_progress(self, current: int, total: int, text: str | None = None) -> None:
        safe_total = max(total, 1)
        safe_current = min(max(current, 0), safe_total)
        self.progress.configure(maximum=safe_total, value=safe_current)
        if text is not None:
            self.set_text(text)

    def reset_progress(self) -> None:
        self.progress.configure(maximum=1, value=0)


class TreePanel(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        on_selected: Callable[[str | None], None],
        on_extract_requested: Callable[[str], None],
    ) -> None:
        super().__init__(master, padding=(8, 4, 4, 8))
        self.on_selected = on_selected
        self.on_extract_requested = on_extract_requested

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(self, show="tree")
        self.tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        self.tree.bind("<Button-3>", self._handle_right_click)

        self.node_cache: dict[tuple[str, ...], str] = {}
        self.item_to_logical: dict[str, str] = {}
        self.context_target_logical: str | None = None

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Extract", command=self._handle_extract_requested)

    def clear(self) -> None:
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        self.node_cache.clear()
        self.item_to_logical.clear()

    def populate(
        self,
        tq_paths: list[str],
        res_paths: list[str],
        on_progress: TreeProgressCallback | None = None,
    ) -> None:
        self.clear()

        tq_root = self.tree.insert("", "end", text="tq", open=True)
        res_root = self.tree.insert("", "end", text="res", open=True)
        self.node_cache[("tq",)] = tq_root
        self.node_cache[("res",)] = res_root

        tq_unique = sorted(set(tq_paths))
        res_unique = sorted(set(res_paths))
        total = len(tq_unique) + len(res_unique)
        done = 0

        if on_progress is not None:
            on_progress(done, total, "Building tree (tq)")

        for logical_path in tq_unique:
            self._insert_logical("tq", logical_path)
            done += 1
            if on_progress is not None and (done % 300 == 0 or done == total):
                on_progress(done, total, "Building tree (tq)")

        if on_progress is not None:
            on_progress(done, total, "Building tree (res)")

        for logical_path in res_unique:
            self._insert_logical("res", logical_path)
            done += 1
            if on_progress is not None and (done % 300 == 0 or done == total):
                on_progress(done, total, "Building tree (res)")

    def _insert_logical(self, root_name: str, logical_path: str) -> None:
        parts = IndexLoader.logical_to_parts(logical_path)
        if not parts:
            return

        # node_cache key: ("tq", "dir", "file.ext") or ("res", ...)
        prefix: tuple[str, ...] = (root_name,)
        parent_id = self.node_cache[prefix]
        for part in parts:
            prefix = (*prefix, part)
            node_id = self.node_cache.get(prefix)
            if node_id is None:
                node_id = self.tree.insert(parent_id, "end", text=part, open=False)
                self.node_cache[prefix] = node_id
            parent_id = node_id
        self.item_to_logical[parent_id] = logical_path

    def _handle_select(self, _event: tk.Event[tk.Misc]) -> None:
        selected = self.tree.selection()
        if not selected:
            self.on_selected(None)
            return
        self.on_selected(self.item_to_logical.get(selected[0]))

    def _handle_right_click(self, event: tk.Event[tk.Misc]) -> None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        self.tree.selection_set(item_id)
        self.context_target_logical = self.item_to_logical.get(item_id)
        state = "normal" if self.context_target_logical else "disabled"
        self.context_menu.entryconfigure("Extract", state=state)

        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _handle_extract_requested(self) -> None:
        if self.context_target_logical:
            self.on_extract_requested(self.context_target_logical)


class HexViewer(ttk.Frame):
    ADDRESS_WIDTH = 10

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(4, 4, 8, 8))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text = tk.Text(
            self,
            wrap="none",
            font=("Consolas", 10),
            undo=False,
        )
        self.text.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.text.tag_config("highlight", foreground="red")
        self.text.config(state="disabled")

    def clear(self) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")

    def render(self, data: bytes, highlight_offset: int, highlight_size: int) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.tag_remove("highlight", "1.0", "end")

        # Fixed-width line format: OFFSET(decimal) + hex bytes + ASCII column.
        for line_offset in range(0, len(data), 16):
            chunk = data[line_offset : line_offset + 16]
            hex_part = " ".join(f"{byte:02X}" for byte in chunk)
            ascii_part = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk)
            line = f"{line_offset:0{self.ADDRESS_WIDTH}d}  {hex_part:<47}  {ascii_part}\n"
            self.text.insert("end", line)

        self._apply_highlight(len(data), highlight_offset, highlight_size)
        self.text.config(state="disabled")

    def _apply_highlight(self, data_size: int, offset: int, size: int) -> None:
        if data_size <= 0 or size <= 0 or offset >= data_size:
            return

        start = max(0, offset)
        end = min(data_size, offset + size)
        if start >= end:
            return

        line_offset = (start // 16) * 16
        while line_offset < end:
            line_start = line_offset
            line_end = min(line_offset + 16, data_size)
            highlight_start = max(line_start, start)
            highlight_end = min(line_end, end)
            if highlight_start < highlight_end:
                first_byte = highlight_start - line_start
                last_byte = highlight_end - line_start - 1
                line_index = line_offset // 16 + 1
                hex_start_col = self.ADDRESS_WIDTH + 2
                start_col = hex_start_col + first_byte * 3
                end_col = hex_start_col + last_byte * 3 + 2
                self.text.tag_add(
                    "highlight",
                    f"{line_index}.{start_col}",
                    f"{line_index}.{end_col}",
                )
            line_offset += 16

        start_line = start // 16 + 1
        self.text.see(f"{start_line}.0")


class ImageViewer(ttk.Frame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, padding=(4, 4, 8, 8))
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self, background="#202020", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        self._photo_image: object | None = None

    def clear(self) -> None:
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self._photo_image = None

    def render(self, image_bytes: bytes) -> tuple[bool, str]:
        if Image is None or ImageTk is None:
            return False, "Pillow is not available. Install pillow first."

        try:
            with Image.open(BytesIO(image_bytes)) as opened:
                image_format = opened.format or "UNKNOWN"
                pil_image = opened.copy()
        except UnidentifiedImageError:
            return False, "Not a supported image stream."
        except Exception as exc:  # noqa: BLE001
            return False, f"Image decode failed: {exc}"

        photo = ImageTk.PhotoImage(pil_image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=photo)
        self.canvas.configure(scrollregion=(0, 0, photo.width(), photo.height()))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._photo_image = photo

        return True, f"{image_format} {pil_image.width}x{pil_image.height}"


class IndexLoader:
    REQUIRED_PATHS = (
        "index_tranquility.txt",
        "tq/resfileindex.txt",
        "ResFiles",
    )

    def validate_root(self, root_path: Path) -> tuple[bool, str]:
        if not root_path.exists():
            return False, f"Path does not exist: {root_path}"
        if not root_path.is_dir():
            return False, f"Not a directory: {root_path}"

        missing: list[str] = []
        for rel in self.REQUIRED_PATHS:
            target = root_path / rel
            if rel == "ResFiles":
                if not target.is_dir():
                    missing.append(rel)
            elif not target.is_file():
                missing.append(rel)

        if missing:
            return False, f"Invalid EVE root. Missing: {', '.join(missing)}"
        return True, ""

    def load(self, root_path: Path) -> LoadedIndexes:
        tq_entries = self._parse_index_file(root_path / "index_tranquility.txt")
        res_entries = self._parse_index_file(root_path / "tq/resfileindex.txt")

        resource_map: dict[str, ResourceEntry] = {}
        for entry in tq_entries + res_entries:
            resource_map[entry.logical_path] = entry

        return LoadedIndexes(
            tq_paths=[entry.logical_path for entry in tq_entries],
            res_paths=[entry.logical_path for entry in res_entries],
            resource_map=resource_map,
        )

    @staticmethod
    def logical_to_parts(logical_path: str) -> list[str]:
        normalized = logical_path.replace("\\", "/").strip()
        lower = normalized.lower()
        if lower.startswith("res:/"):
            normalized = normalized[5:]
        normalized = normalized.strip("/")
        if not normalized:
            return []
        return [part for part in normalized.split("/") if part]

    def resolve_physical_relative(self, entry: ResourceEntry) -> str | None:
        physical = entry.physical_path.strip().replace("\\", "/")
        if not physical and entry.hash_value:
            hash_value = entry.hash_value.lower()
            if len(hash_value) >= 2:
                physical = f"{hash_value[:2]}/{hash_value}"

        physical = physical.strip("/")
        if not physical:
            return None

        lowered = physical.lower()
        if lowered.startswith("resfiles/"):
            physical = physical.split("/", 1)[1]

        parts = [part for part in physical.split("/") if part]
        if len(parts) >= 2:
            relative = Path(parts[0]) / parts[1]
        elif len(parts) == 1:
            token = parts[0]
            if entry.hash_value and len(entry.hash_value) >= 2:
                relative = Path(entry.hash_value[:2].lower()) / token
            elif len(token) >= 2:
                relative = Path(token[:2].lower()) / token
            else:
                return None
        else:
            return None
        return relative.as_posix()

    def resolve_physical_path(self, root_path: Path, entry: ResourceEntry) -> Path | None:
        relative = self.resolve_physical_relative(entry)
        if relative is None:
            return None
        return root_path / "ResFiles" / relative

    def _parse_index_file(self, index_path: Path) -> list[ResourceEntry]:
        entries: list[ResourceEntry] = []
        with index_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                entry = self._parse_line(line)
                if entry is not None:
                    entries.append(entry)
        return entries

    def _parse_line(self, line: str) -> ResourceEntry | None:
        raw = line.strip()
        if not raw or raw.startswith("#"):
            return None

        parts = [part.strip().strip('"') for part in raw.split(",")]
        if not parts:
            return None

        logical = self._normalize_logical(parts[0])
        if not logical:
            return None

        fields = [field for field in parts[1:] if field]
        # Index formats may vary; extract best-effort metadata from remaining fields.
        physical_path = self._extract_physical_path(fields)
        hash_value = self._extract_hash(fields)
        offset, size = self._extract_offset_size(fields)

        if not physical_path and hash_value:
            physical_path = f"{hash_value[:2].lower()}/{hash_value.lower()}"

        return ResourceEntry(
            logical_path=logical,
            physical_path=physical_path,
            hash_value=hash_value,
            offset=offset,
            size=size,
        )

    @staticmethod
    def _normalize_logical(value: str) -> str:
        token = value.strip().strip('"').replace("\\", "/")
        if not token:
            return ""
        if token.lower().startswith("res:/"):
            token = token[5:]
        token = token.strip("/")
        if not token:
            return ""
        return f"res:/{token}"

    @staticmethod
    def _extract_physical_path(fields: list[str]) -> str:
        normalized = [field.replace("\\", "/").strip().strip('"') for field in fields]

        for field in normalized:
            lower = field.lower()
            if "/" in field and not lower.startswith("res:/"):
                cleaned = field.strip("/")
                if cleaned and not cleaned.lower().startswith("resfiles/"):
                    return cleaned
                if cleaned.lower().startswith("resfiles/"):
                    return cleaned.split("/", 1)[1]

        for i in range(len(normalized) - 1):
            if re.fullmatch(r"[0-9a-fA-F]{2}", normalized[i]):
                if normalized[i + 1]:
                    return f"{normalized[i].lower()}/{normalized[i + 1]}"
        return ""

    @staticmethod
    def _extract_hash(fields: list[str]) -> str:
        for field in fields:
            token = field.strip().strip('"')
            compact = token.replace("_", "")
            if re.fullmatch(r"[0-9a-fA-F]{8,128}", compact):
                return compact.lower()
        return ""

    def _extract_offset_size(self, fields: list[str]) -> tuple[int, int]:
        numbers: list[int] = []
        for field in fields:
            maybe = self._parse_integer(field)
            if maybe is not None:
                numbers.append(maybe)
        if len(numbers) >= 2:
            return max(numbers[-2], 0), max(numbers[-1], 0)
        if len(numbers) == 1:
            return max(numbers[0], 0), 0
        return 0, 0

    @staticmethod
    def _parse_integer(text: str) -> int | None:
        token = text.strip().lower()
        if not token:
            return None
        if token.startswith("0x"):
            try:
                return int(token, 16)
            except ValueError:
                return None
        if re.fullmatch(r"\d+", token):
            try:
                return int(token)
            except ValueError:
                return None
        return None


class EVEApp:
    LARGE_FILE_THRESHOLD    = 10 * 1024 * 1024
    REMOTE_BASE_URL         = "https://resources.eveonline.com"
    DEFAULT_EXTRACT_DIR     = Path(r"E:\myGames-Resources\EVE-DAT")
    IMAGE_EXTENSIONS        = {
        ".png",
        ".dds",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".tga",
        ".gif",
        ".webp",
        ".tif",
        ".tiff",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("EVE Resource Explorer")
        self.root.geometry("1280x780")
        self.root.minsize(960, 600)

        self.loader = IndexLoader()
        self.loaded_indexes: LoadedIndexes | None = None
        self.current_root_path: Path | None = None
        self.cache_dir = Path(__file__).resolve().parent / ".cache"

        self._build_toolbar()
        self._build_mainframe()
        self._build_statusbar()
        
    def _build_toolbar(self) -> None:
        self.toolbar = Toolbar(self.root,
            on_open_clicked=self._select_root_directory,
            on_path_entered=self._load_from_path_text,
        )
        self.toolbar.pack(fill="x", side="top")
        
    def _build_mainframe(self) -> None:
        self.pane = ttk.Panedwindow(self.root, orient="horizontal")
        self.pane.pack(fill="both", expand=True)

        self.tree_panel = TreePanel(
            self.pane,
            on_selected=self._on_tree_selected,
            on_extract_requested=self._extract_resource_to_folder,
        )
        self.preview_panel = ttk.Frame(self.pane)
        self.preview_panel.rowconfigure(0, weight=1)
        self.preview_panel.columnconfigure(0, weight=1)

        self.hex_viewer = HexViewer(self.preview_panel)
        self.image_viewer = ImageViewer(self.preview_panel)
        self.hex_viewer.grid(row=0, column=0, sticky="nsew")
        self.image_viewer.grid(row=0, column=0, sticky="nsew")
        self._show_hex_view()

        self.pane.add(self.tree_panel, weight=1)
        self.pane.add(self.preview_panel, weight=3)

    def _build_statusbar(self) -> None:
        self.status_bar = StatusBar(self.root)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_bar.set_text("Select EVE root path.")
        
        
        
        
    def _select_root_directory(self) -> None:
        selected = filedialog.askdirectory(title="Select EVE Root Directory")
        if not selected:
            return
        self.toolbar.set_path(selected)
        self._load_root(Path(selected))

    def _load_from_path_text(self, path_text: str) -> None:
        if not path_text:
            return
        self._load_root(Path(path_text))

    def _load_root(self, root_path: Path) -> None:
        valid, error = self.loader.validate_root(root_path)
        if not valid:
            messagebox.showerror("Invalid EVE Root", error)
            self.status_bar.set_text(error)
            self.status_bar.reset_progress()
            return

        try:
            loaded = self.loader.load(root_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Load Error", f"Failed to parse index files:\n{exc}")
            self.status_bar.set_text("Failed to parse index files.")
            self.status_bar.reset_progress()
            return

        self.current_root_path = root_path
        self.loaded_indexes = loaded
        total_items = len(set(loaded.tq_paths)) + len(set(loaded.res_paths))
        self.status_bar.set_progress(0, total_items, f"Building tree... 0/{total_items}")
        self.root.update_idletasks()
        self.tree_panel.populate(
            loaded.tq_paths,
            loaded.res_paths,
            on_progress=self._on_tree_build_progress,
        )
        self.hex_viewer.clear()
        self.image_viewer.clear()
        self._show_hex_view()
        self.status_bar.reset_progress()
        self.status_bar.set_text(
            f"Loaded: {root_path} | tq={len(loaded.tq_paths)} res={len(loaded.res_paths)}"
        )

    def _on_tree_build_progress(self, current: int, total: int, phase: str) -> None:
        self.status_bar.set_progress(current, total, f"{phase}... {current}/{max(total, 1)}")
        self.root.update_idletasks()

    def _show_hex_view(self) -> None:
        self.image_viewer.grid_remove()
        self.hex_viewer.grid()

    def _show_image_view(self) -> None:
        self.hex_viewer.grid_remove()
        self.image_viewer.grid()

    def _resource_slice(self, data: bytes, offset: int, size: int) -> bytes:
        if size <= 0 or offset < 0 or offset >= len(data):
            return data
        end = min(offset + size, len(data))
        if end <= offset:
            return data
        return data[offset:end]

    def _is_image_resource(self, logical_path: str) -> bool:
        parts = IndexLoader.logical_to_parts(logical_path)
        if not parts:
            return False
        suffix = Path(parts[-1]).suffix.lower()
        return suffix in self.IMAGE_EXTENSIONS

    def _on_tree_selected(self, logical_path: str | None) -> None:
        if not logical_path:
            return
        if self.loaded_indexes is None or self.current_root_path is None:
            return

        entry = self.loaded_indexes.resource_map.get(logical_path)
        if entry is None:
            self.status_bar.set_text(f"Logical path not found in map: {logical_path}")
            return

        relative_physical = self.loader.resolve_physical_relative(entry)
        if relative_physical is None:
            self.status_bar.set_text(f"Unable to resolve physical path for: {logical_path}")
            return

        data, source_file, source_label = self._load_resource_bytes(relative_physical)
        if data is None or source_file is None:
            return

        payload = self._resource_slice(data, entry.offset, entry.size)
        image_preview_error = ""

        if self._is_image_resource(logical_path):
            rendered, image_info = self.image_viewer.render(payload)
            if not rendered and payload is not data:
                rendered, image_info = self.image_viewer.render(data)

            if rendered:
                self._show_image_view()
                physical_display = entry.physical_path or "(unknown)"
                self.status_bar.set_text(
                    " | ".join(
                        [
                            f"Logical: {entry.logical_path}",
                            f"Physical: {physical_display}",
                            f"Source: {source_label} ({source_file})",
                            f"Container Size: {len(data)} bytes",
                            f"Preview: image ({image_info})",
                        ]
                    )
                )
                return
            image_preview_error = image_info

        self._show_hex_view()
        if len(data) >= self.LARGE_FILE_THRESHOLD:
            messagebox.showwarning(
                "Large File",
                f"File size is {len(data):,} bytes (>= 10MB).\nRendering full hex view may be slow.",
            )

        self.hex_viewer.render(data, entry.offset, entry.size)

        physical_display = entry.physical_path or "(unknown)"
        self.status_bar.set_text(
            " | ".join(
                [
                    f"Logical: {entry.logical_path}",
                    f"Physical: {physical_display}",
                    f"Source: {source_label} ({source_file})",
                    f"Container Size: {len(data)} bytes",
                    f"Highlight: offset={entry.offset} size={entry.size}",
                    f"Preview: hex{f' (image decode failed: {image_preview_error})' if image_preview_error else ''}",
                ]
            )
        )

    def _extract_resource_to_folder(self, logical_path: str) -> None:
        if self.loaded_indexes is None or self.current_root_path is None:
            messagebox.showerror("Extract Error", "No EVE root is loaded.")
            return

        entry = self.loaded_indexes.resource_map.get(logical_path)
        if entry is None:
            messagebox.showerror("Extract Error", f"Logical path not found:\n{logical_path}")
            self.status_bar.set_text(f"Extract failed: logical path not found ({logical_path})")
            return

        relative_physical = self.loader.resolve_physical_relative(entry)
        source_path, source_label = self._find_extract_source(relative_physical)
        if source_path is None:
            messagebox.showerror(
                "Extract Error",
                "Source file does not exist in local ResFiles or cache.\n"
                f"Logical: {logical_path}\n"
                f"Physical: {entry.physical_path or '(unknown)'}",
            )
            self.status_bar.set_text(f"Extract failed: source not found ({logical_path})")
            return

        selected_dir = filedialog.askdirectory(
            title="Select Extract Destination",
            initialdir=str(self.DEFAULT_EXTRACT_DIR),
        )
        if not selected_dir:
            return

        logical_relative = self._logical_relative_path(logical_path)
        if logical_relative is None:
            messagebox.showerror("Extract Error", f"Invalid logical path:\n{logical_path}")
            self.status_bar.set_text(f"Extract failed: invalid logical path ({logical_path})")
            return

        destination_path = Path(selected_dir) / logical_relative
        try:
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination_path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "Extract Error",
                f"Failed to extract file:\n{source_path}\n->\n{destination_path}\n\n{exc}",
            )
            self.status_bar.set_text(f"Extract failed: {logical_path}")
            return

        self.status_bar.set_text(
            f"Extracted ({source_label}): {logical_path} -> {destination_path}"
        )

    @staticmethod
    def _logical_relative_path(logical_path: str) -> Path | None:
        parts = IndexLoader.logical_to_parts(logical_path)
        if not parts:
            return None

        for part in parts:
            if part in ("", ".", ".."):
                return None

        return Path(*parts)

    def _find_extract_source(self, relative_physical: str | None) -> tuple[Path | None, str]:
        if self.current_root_path is None or not relative_physical:
            return None, ""

        relative = relative_physical.replace("\\", "/").strip("/")
        local_path = self.current_root_path / "ResFiles" / Path(relative)
        if local_path.is_file():
            return local_path, "local"

        cache_path = self.cache_dir / Path(relative)
        if cache_path.is_file():
            return cache_path, "cache"

        return None, ""

    def _load_resource_bytes(self, relative_physical: str) -> tuple[bytes | None, Path | None, str]:
        if self.current_root_path is None:
            return None, None, ""

        relative = relative_physical.replace("\\", "/").strip("/")
        local_path = self.current_root_path / "ResFiles" / Path(relative)
        if local_path.is_file():
            try:
                return local_path.read_bytes(), local_path, "local"
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Read Error", f"Failed to read local file:\n{exc}")
                self.status_bar.set_text(f"Read failed: {local_path}")
                return None, None, ""

        cache_path = self.cache_dir / Path(relative)
        if cache_path.is_file():
            try:
                return cache_path.read_bytes(), cache_path, "cache"
            except Exception as exc:  # noqa: BLE001
                messagebox.showerror("Read Error", f"Failed to read cache file:\n{exc}")
                self.status_bar.set_text(f"Read failed: {cache_path}")
                return None, None, ""

        url = f"{self.REMOTE_BASE_URL}/{relative}"
        self.status_bar.set_text(f"Downloading: {url}")
        self.root.update_idletasks()

        try:
            downloaded = self._download_remote_bytes(relative)
        except HTTPError as exc:
            messagebox.showerror("Download Error", f"HTTP {exc.code} while downloading:\n{url}")
            self.status_bar.set_text(f"Download failed (HTTP {exc.code}): {relative}")
            return None, None, ""
        except URLError as exc:
            messagebox.showerror("Download Error", f"Network error while downloading:\n{url}\n{exc}")
            self.status_bar.set_text(f"Download failed: {relative}")
            return None, None, ""
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Download Error", f"Unexpected error while downloading:\n{exc}")
            self.status_bar.set_text(f"Download failed: {relative}")
            return None, None, ""

        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(downloaded)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning(
                "Cache Warning",
                f"Downloaded but failed to write cache file:\n{cache_path}\n{exc}",
            )
            self.status_bar.set_text(f"Downloaded without cache: {relative}")
            return downloaded, cache_path, "remote"

        return downloaded, cache_path, "remote+cache"

    def _download_remote_bytes(self, relative_physical: str) -> bytes:
        relative = relative_physical.replace("\\", "/").strip("/")
        encoded_relative = quote(relative, safe="/-._~")
        url = f"{self.REMOTE_BASE_URL}/{encoded_relative}"

        # Some CDNs reject urllib default User-Agent and require browser-like headers.
        header_profiles = [
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
            {
                "User-Agent": "EVE-Resource-Explorer/1.0",
                "Accept": "*/*",
                "Accept-Encoding": "identity",
                "Connection": "close",
            },
        ]

        last_http_error: HTTPError | None = None
        for headers in header_profiles:
            request = Request(url=url, headers=headers, method="GET")
            try:
                with urlopen(request, timeout=30) as response:
                    return response.read()
            except HTTPError as exc:
                last_http_error = exc
                if exc.code in (403, 406, 429):
                    continue
                raise

        if last_http_error is not None:
            raise last_http_error
        raise HTTPError(url, 500, "Download failed without HTTP response", None, None)


def main() -> None:
    root = tk.Tk()
    app = EVEApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
