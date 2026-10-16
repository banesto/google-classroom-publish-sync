"""Tk dialogs keep the ordinary workflow usable from Explorer without a terminal."""
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk


class UI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
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
        win.geometry('760x660')
        ttk.Label(win, text=f'{pub.email}\n{pub.url}\nMy Drive / ' + ' / '.join(pub.drive_path),
                  wraplength=720, padding=12).pack(fill='x')
        box = tk.Text(win, wrap='word', height=12)
        box.pack(fill='both', expand=True, padx=12)
        box.insert('1.0', pub.text)
        ttk.Label(win, text=f'{len(pub.names)} existing Drive files, in this order:').pack(pady=8)
        names = tk.Listbox(win, height=8)
        names.pack(fill='x', padx=12)
        for name in pub.names:
            names.insert('end', name)
        result = []
        def accept():
            value = box.get('1.0', 'end-1c').strip()
            if not value or value.splitlines()[0] != pub.text.splitlines()[0]:
                messagebox.showerror('Check post', 'Keep subject and date as the first line.', parent=win)
                return
            result.append(value)
            win.destroy()
        buttons = ttk.Frame(win, padding=12)
        buttons.pack()
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
        from .core import MARKER, PENDING, confirm
        if (folder / MARKER).exists():
            raise ValueError('A success marker already exists. Do not clear it or repost.')
        record = json.loads((folder / PENDING).read_text(encoding='utf-8'))
        self.document('Unresolved attempt — inspect this class in Chrome',
                      f"Account: {record['email']}\nClass: {record['class_url']}\n"
                      f"Stage: {record.get('stage', 'unknown')}\n\n{record['text']}\n\n"
                      + '\n'.join(record['names']) +
                      '\n\nUse the saved child profile to inspect the Stream. '
                      'Compare author, text, attachment names/count and order after a reload. '
                      'Never clear this attempt just because the request timed out.')
        choice = simpledialog.askstring('Recovery',
                     'Type VERIFIED if the full post exists, ABSENT if definitely not published,\n'
                     'or Cancel to keep the attempt blocked.', parent=self.root)
        if choice == 'VERIFIED':
            url = simpledialog.askstring('Post link', 'Paste the post link if available (blank is OK).', parent=self.root)
            if url is not None:
                confirm(folder, url.strip())
                self.info('Recovered', 'Success marker saved. This folder cannot be published again.')
        elif choice == 'ABSENT':
            if self.ask('Allow a later retry?', 'Have you confirmed no post exists, and closed every old composer?\n'
                        'Only then clear this pending attempt. The next publication will be a new attempt.'):
                (folder / PENDING).unlink()

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
                target = filedialog.askdirectory(title='Select the YYYY.MM.DD publication folder', parent=win)
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
