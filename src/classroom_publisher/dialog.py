"""Tk dialogs keep the ordinary workflow usable from Explorer without a terminal."""
import tkinter as tk
import sys
from tkinter import filedialog, messagebox, ttk
from .icons import icon_path


class UI:
    def __init__(self):
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('ClassroomPublisher.Desktop')
        self.root = tk.Tk()
        self.root.withdraw()
        self.icon = tk.PhotoImage(file=str(icon_path(extension='png')))
        self.root.iconphoto(True, self.icon)
        if sys.platform == 'win32':
            self.root.iconbitmap(default=str(icon_path()))
        self.progress = None

    def close(self):
        self.root.destroy()

    def info(self, title, text):
        messagebox.showinfo(title, text, parent=self.root)

    def error(self, text):
        self.document('Stopped — nothing further will be posted', text)

    def document(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.geometry('760x540')
        frame = ttk.Frame(win, padding=12)
        frame.pack(fill='both', expand=True)
        box = tk.Text(frame, wrap='word')
        bar = ttk.Scrollbar(frame, command=box.yview)
        box.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        box.pack(fill='both', expand=True)
        box.insert('1.0', text)
        box.configure(state='disabled')
        ttk.Button(win, text='Close', command=win.destroy).pack(pady=8)
        win.grab_set()
        self.root.wait_window(win)

    def ask(self, title, text):
        return messagebox.askyesno(title, text, parent=self.root)

    def status(self, text):
        if self.progress is None or not self.progress.winfo_exists():
            self.progress = tk.Toplevel(self.root)
            self.progress.title('Classroom Publisher')
            self.progress.geometry('600x120')
            self.progress.protocol('WM_DELETE_WINDOW', lambda: None)
            self.status_label = ttk.Label(self.progress, wraplength=570, padding=15)
            self.status_label.pack(fill='both', expand=True)
        self.status_label.configure(text=text)
        self.root.update()

    def edit(self, pub):
        win = tk.Toplevel(self.root)
        win.title('Review Classroom post')
        width = min(680, win.winfo_screenwidth() - 60)
        height = min(440, win.winfo_screenheight() - 100)
        win.geometry(f'{width}x{height}')
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        ttk.Label(win, text=f'{pub.email}\n{pub.url}\nMy Drive / ' + ' / '.join(pub.drive_path),
                  wraplength=width - 40, padding=12).grid(row=0, column=0, sticky='ew')
        box = tk.Text(win, wrap='word', height=4)
        box.grid(row=1, column=0, sticky='nsew', padx=12)
        box.insert('1.0', pub.text)
        ttk.Label(win, text=f'{len(pub.names)} existing Drive files, in this order:').grid(row=2, column=0, pady=6)
        file_frame = ttk.Frame(win)
        file_frame.grid(row=3, column=0, sticky='ew', padx=12)
        names = tk.Listbox(file_frame, height=4)
        scrollbar = ttk.Scrollbar(file_frame, orient='vertical', command=names.yview)
        names.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        names.pack(side='left', fill='x', expand=True)
        for name in pub.names:
            names.insert('end', name)
        result = []
        def accept():
            value = box.get('1.0', 'end-1c').strip()
            if not value:
                messagebox.showerror('Check post', 'Enter some text for the post.', parent=win)
                return
            result.append(value)
            win.destroy()
        buttons = ttk.Frame(win, padding=12)
        buttons.grid(row=4, column=0)
        ttk.Button(buttons, text='Cancel', command=win.destroy).pack(side='left', padx=8)
        ttk.Button(buttons, text='Prepare in Classroom', command=accept).pack(side='left')
        win.grab_set()
        self.root.wait_window(win)
        return result[0] if result else None

    def review_draft(self, pub):
        return self.ask('Publish to Classroom?',
                        f'The draft for {pub.email} has {len(pub.names)} verified Drive attachments.\n\n'
                        'Review the visible browser draft. Publish this post now?\n\n'
                        'Choose No to stop. Do not click Post in Chrome yourself.')

    def recover(self, folder):
        import json
        from .core import MARKER, PENDING, allow_retry
        if (folder / MARKER).exists():
            raise ValueError('A success marker already exists. Do not clear it or repost.')
        record = json.loads((folder / PENDING).read_text(encoding='utf-8'))
        win = tk.Toplevel(self.root)
        win.title('Previous publication attempt')
        win.geometry('680x440')
        win.columnconfigure(0, weight=1)
        win.rowconfigure(2, weight=1)
        ttk.Label(win, text='Check the class Stream before choosing Retry publishing.\n'
                  'Retry means no post exists and any old draft is closed.\n'
                  'If the post exists or you are unsure, choose Cancel publication.',
                  wraplength=640, padding=12).grid(row=0, column=0, sticky='ew')
        ttk.Label(win, text=f"Account: {record['email']}\nStatus: {record.get('stage', 'unknown')}\n"
                  f"Class: {record['class_url']}\n"
                  'Edit the post text below:', wraplength=640, padding=8).grid(row=1, column=0, sticky='ew')
        details = tk.Text(win, wrap='word', height=4)
        details.grid(row=2, column=0, sticky='nsew', padx=12)
        details.insert('1.0', record['text'])
        names = tk.Listbox(win, height=3)
        names.grid(row=3, column=0, sticky='ew', padx=12, pady=6)
        for name in record['names']:
            names.insert('end', name)
        retry = []
        def choose_retry():
            text = details.get('1.0', 'end-1c').strip()
            if not text:
                messagebox.showerror('Check post', 'Enter some text for the post.', parent=win)
                return
            retry.append(text)
            win.destroy()
        buttons = ttk.Frame(win, padding=12)
        buttons.grid(row=4, column=0)
        ttk.Button(buttons, text='Cancel publication', command=win.destroy).pack(side='left', padx=8)
        ttk.Button(buttons, text='Retry publishing', command=choose_retry).pack(side='left')
        win.grab_set()
        self.root.wait_window(win)
        if retry:
            allow_retry(folder, retry[0])
            return True
        return False

    def choose_action(self, config, config_path):
        win = tk.Toplevel(self.root)
        win.title('Classroom Publisher')
        win.geometry('650x340')
        ttk.Label(win, text='Publish existing Drive files to a child’s Classroom Stream', padding=15).pack()
        keys = list(config.get('children', {}))
        child = tk.StringVar(value=keys[0] if keys else '')
        picker = ttk.Combobox(win, textvariable=child, values=keys, state='readonly')
        picker.pack(fill='x', padx=25, pady=8)
        result = []
        def action(command, target=None):
            if command in ('publish', 'validate', 'reconcile'):
                target = filedialog.askdirectory(title='Select the folder to publish', parent=win)
                if not target:
                    return
            result.extend([command, target])
            win.destroy()
        row = ttk.Frame(win)
        row.pack(pady=10)
        ttk.Button(row, text='Sign in / inspect class', command=lambda: action('login', child.get())).pack(side='left', padx=5)
        ttk.Button(row, text='Edit configuration', command=lambda: action('edit-config')).pack(side='left', padx=5)
        for label, command in [('Publish a folder', 'publish'), ('Validate a folder', 'validate'), ('Recover an uncertain attempt', 'reconcile')]:
            ttk.Button(win, text=label, command=lambda c=command: action(c)).pack(fill='x', padx=100, pady=5)
        ttk.Label(win, text=str(config_path), wraplength=610, padding=10).pack()
        self.root.wait_window(win)
        return result or None
