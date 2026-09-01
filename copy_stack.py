#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Copy Stack — حافظة متعددة النسخ
================================
برنامج يراقب الحافظة (Clipboard) تلقائياً: كل ما تنسخه (Ctrl+C أو من قائمة
الماوس) من أي برنامج أو صفحة يُضاف إلى القائمة، وبعدها تستطيع:

  • لصق الكل دفعة واحدة (يجمع كل العناصر في الحافظة ثم تلصقها بـ Ctrl+V)
  • اختيار عناصر معينة فقط ولصقها
  • النقر المزدوج على أي عنصر لنسخه وحده

التشغيل:  python copy_stack.py
المتطلبات: pip install pyperclip
"""

import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import pyperclip
except ImportError:
    raise SystemExit(
        "مكتبة pyperclip غير مثبتة. ثبّتها بالأمر:\n\n    pip install pyperclip\n"
    )

POLL_INTERVAL = 0.4  # ثوانٍ بين كل فحص للحافظة

SEPARATORS = {
    "سطر جديد": "\n",
    "سطر فارغ بينهم": "\n\n",
    "مسافة": " ",
    "فاصلة": "، ",
}


class ClipboardMonitor(threading.Thread):
    """خيط يراقب الحافظة ويستدعي callback عند وجود نص جديد."""

    def __init__(self, on_new_text):
        super().__init__(daemon=True)
        self.on_new_text = on_new_text
        self.last_text = None
        self.paused = False
        self.ignore_next = None  # نص وضعناه نحن في الحافظة فلا نلتقطه من جديد
        self._stop_event = threading.Event()

    def run(self):
        try:
            self.last_text = pyperclip.paste()
        except Exception:
            self.last_text = None
        while not self._stop_event.is_set():
            time.sleep(POLL_INTERVAL)
            if self.paused:
                continue
            try:
                text = pyperclip.paste()
            except Exception:
                continue
            if not text or text == self.last_text:
                continue
            self.last_text = text
            if self.ignore_next is not None and text == self.ignore_next:
                self.ignore_next = None
                continue
            self.on_new_text(text)

    def set_clipboard(self, text):
        """يضع نصاً في الحافظة دون أن يلتقطه المراقب كعنصر جديد."""
        self.ignore_next = text
        self.last_text = text
        pyperclip.copy(text)

    def stop(self):
        self._stop_event.set()


class CopyStackApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.items: list[str] = []
        self._toast = None  # نافذة الإشعار الصغيرة

        root.title("Copy Stack — حافظة متعددة النسخ")
        root.geometry("560x520")
        root.minsize(420, 380)
        root.attributes("-topmost", True)

        self.monitor = ClipboardMonitor(self._on_new_text)

        self._build_ui()
        self.monitor.start()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")

        self.status_var = tk.StringVar(value="المراقبة تعمل ✅ — انسخ من أي مكان وسيظهر هنا")
        ttk.Label(top, textvariable=self.status_var, anchor="e").pack(fill="x")

        # قائمة العناصر
        mid = ttk.Frame(self.root, padding=(10, 0))
        mid.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(mid)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(
            mid,
            selectmode="extended",
            activestyle="dotbox",
            font=("Segoe UI", 11),
            justify="right",
            yscrollcommand=scrollbar.set,
        )
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        self.listbox.bind("<Double-Button-1>", self._copy_one)
        self.listbox.bind("<Delete>", lambda e: self.delete_selected())

        # خيارات الفاصل
        opts = ttk.Frame(self.root, padding=(10, 6))
        opts.pack(fill="x")
        ttk.Label(opts, text="الفاصل بين العناصر عند الجمع:").pack(side="right", padx=(6, 0))
        self.sep_var = tk.StringVar(value="سطر جديد")
        sep_box = ttk.Combobox(
            opts,
            textvariable=self.sep_var,
            values=list(SEPARATORS.keys()),
            state="readonly",
            width=14,
            justify="right",
        )
        sep_box.pack(side="right")

        self.topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts,
            text="النافذة دائماً في المقدمة",
            variable=self.topmost_var,
            command=lambda: self.root.attributes("-topmost", self.topmost_var.get()),
        ).pack(side="left")

        opts2 = ttk.Frame(self.root, padding=(10, 0))
        opts2.pack(fill="x")
        self.number_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts2,
            text="ترقيم العناصر عند اللصق (1. ... 2. ...)",
            variable=self.number_var,
        ).pack(side="right")
        self.toast_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts2,
            text="إشعار عند كل نسخة",
            variable=self.toast_var,
        ).pack(side="left")

        # الأزرار
        btns = ttk.Frame(self.root, padding=(10, 4))
        btns.pack(fill="x")

        ttk.Button(btns, text="📋 نسخ الكل للصق", command=self.copy_all).pack(
            side="right", padx=3, pady=3
        )
        ttk.Button(btns, text="✅ نسخ المحدد فقط", command=self.copy_selected).pack(
            side="right", padx=3, pady=3
        )
        ttk.Button(btns, text="🗑 حذف المحدد", command=self.delete_selected).pack(
            side="right", padx=3, pady=3
        )
        ttk.Button(btns, text="🧹 مسح الكل", command=self.clear_all).pack(
            side="right", padx=3, pady=3
        )

        btns2 = ttk.Frame(self.root, padding=(10, 0))
        btns2.pack(fill="x")
        self.pause_btn = ttk.Button(btns2, text="⏸ إيقاف المراقبة مؤقتاً", command=self.toggle_pause)
        self.pause_btn.pack(side="right", padx=3, pady=(0, 8))

        hint = ttk.Label(
            self.root,
            text="نقرة مزدوجة على عنصر = نسخه وحده • Ctrl/Shift للتحديد المتعدد • Delete للحذف",
            anchor="e",
            foreground="#666",
            padding=(10, 0, 10, 8),
        )
        hint.pack(fill="x")

    # -------------------------------------------------------------- Events
    def _on_new_text(self, text: str):
        # يُستدعى من خيط المراقبة — ننقل التنفيذ لخيط الواجهة
        self.root.after(0, self._add_item, text)

    @staticmethod
    def _label(n: int, text: str) -> str:
        preview = " ".join(text.split())
        if len(preview) > 70:
            preview = preview[:67] + "..."
        return f"📄 نسخة {n}: {preview}"

    def _add_item(self, text: str):
        self.items.append(text)
        n = len(self.items)
        self.listbox.insert("end", self._label(n, text))
        self.listbox.see("end")
        self.status_var.set(f"✅ نسخة {n} محفوظة — المجموع: {n}")
        if self.toast_var.get():
            self._show_toast(f"نسخة {n} ✅")

    def _show_toast(self, message: str):
        """إشعار صغير أسفل يمين الشاشة يختفي تلقائياً."""
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        toast = tk.Toplevel(self.root)
        self._toast = toast
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        label = tk.Label(
            toast,
            text=message,
            font=("Segoe UI", 12, "bold"),
            bg="#2e7d32",
            fg="white",
            padx=18,
            pady=10,
        )
        label.pack()
        toast.update_idletasks()
        sw, sh = toast.winfo_screenwidth(), toast.winfo_screenheight()
        w, h = toast.winfo_width(), toast.winfo_height()
        toast.geometry(f"+{sw - w - 24}+{sh - h - 72}")
        toast.after(1500, toast.destroy)

    def _copy_one(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        text = self.items[sel[0]]
        self.monitor.set_clipboard(text)
        self.status_var.set("تم نسخ العنصر ✅ — اذهب والصقه بـ Ctrl+V")

    # ------------------------------------------------------------- Actions
    def _join(self, texts):
        sep = SEPARATORS.get(self.sep_var.get(), "\n")
        if self.number_var.get():
            texts = [f"{n}. {t}" for n, t in enumerate(texts, start=1)]
        return sep.join(texts)

    def copy_all(self):
        if not self.items:
            messagebox.showinfo("Copy Stack", "القائمة فارغة — انسخ شيئاً أولاً.")
            return
        self.monitor.set_clipboard(self._join(self.items))
        self.status_var.set(
            f"تم تجهيز {len(self.items)} عنصراً في الحافظة ✅ — اذهب للإيميل والصق بـ Ctrl+V"
        )

    def copy_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showinfo("Copy Stack", "حدد عنصراً أو أكثر من القائمة أولاً.")
            return
        texts = [self.items[i] for i in sel]
        self.monitor.set_clipboard(self._join(texts))
        self.status_var.set(
            f"تم تجهيز {len(texts)} من العناصر المحددة ✅ — الصق بـ Ctrl+V"
        )

    def delete_selected(self):
        sel = list(self.listbox.curselection())
        if not sel:
            return
        for i in reversed(sel):
            del self.items[i]
        self._refresh_list()
        self.status_var.set(f"تم الحذف — المتبقي: {len(self.items)}")

    def clear_all(self):
        if self.items and not messagebox.askyesno("Copy Stack", "مسح كل العناصر؟"):
            return
        self.items.clear()
        self._refresh_list()
        self.status_var.set("تم مسح القائمة — ابدأ النسخ من جديد")

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for n, text in enumerate(self.items, start=1):
            self.listbox.insert("end", self._label(n, text))

    def toggle_pause(self):
        self.monitor.paused = not self.monitor.paused
        if self.monitor.paused:
            self.pause_btn.config(text="▶ استئناف المراقبة")
            self.status_var.set("المراقبة متوقفة مؤقتاً ⏸")
        else:
            self.pause_btn.config(text="⏸ إيقاف المراقبة مؤقتاً")
            self.status_var.set("المراقبة تعمل ✅")

    def _on_close(self):
        self.monitor.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except tk.TclError:
        pass
    CopyStackApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
