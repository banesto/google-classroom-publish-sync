import argparse
import json
import sys
from pathlib import Path
from .config import data_dir, load_config
from .core import MARKER, PENDING, prepare
from .locking import single_instance


def prepare_for_publish(target, config, base, ui):
    folder = Path(target).resolve(strict=True)
    if (folder / PENDING).exists() and not (folder / MARKER).exists():
        # Recovery must explicitly authorize a retry. Cancellation and VERIFIED
        # both stop here; never infer permission merely from a missing file.
        if ui.recover(folder) is not True:
            return None
    return prepare(folder, config, base)


def main():
    parser = argparse.ArgumentParser(description='Publish existing Drive files using a child-specific Chrome session')
    parser.add_argument('command', nargs='?', default='gui', choices=[
        'gui', 'validate', 'publish', 'login', 'inspect', 'reconcile', 'context-menu', 'edit-config'])
    parser.add_argument('target', nargs='?', help='Publication folder, child key, or context-menu install/remove')
    parser.add_argument('--config', type=Path, default=data_dir() / 'config.json')
    parser.add_argument('--gui', action='store_true', help='Show errors in a dialog (used by Explorer)')
    args = parser.parse_args()
    ui = None
    try:
        if args.command == 'context-menu':
            if args.target not in ('install', 'remove'):
                raise ValueError('Use context-menu install or context-menu remove.')
            from .integration import context_menu
            context_menu(args.target, args.config)
            return
        from .dialog import UI
        if args.command != 'validate' or args.gui:
            ui = UI()
        # All installs for this OS user serialize publish, login, recovery and inspection.
        with single_instance(data_dir() / 'publisher.lock'):
            if args.command == 'gui':
                raw = json.loads(args.config.read_text(encoding='utf-8-sig'))
                chosen = ui.choose_action(raw, args.config)
                if chosen is None:
                    return
                args.command, args.target = chosen
            if args.command == 'edit-config':
                from .integration import open_file
                open_file(args.config.resolve())
                return
            config, base = load_config(args.config)
            if not args.target:
                raise ValueError('Choose a child key or publication folder.')
            if args.command in ('login', 'inspect'):
                if args.target not in config['children']:
                    raise ValueError('Unknown child key: ' + args.target)
                if not any(c['child'] == args.target for c in config['classes']):
                    raise ValueError('Configure at least one class for this child first.')
                from .browser import sign_in
                sign_in(args.target, config, base, ui, inspect=args.command == 'inspect')
            elif args.command == 'reconcile':
                ui.recover(Path(args.target).resolve(strict=True))
            else:
                pub = (prepare_for_publish(args.target, config, base, ui)
                       if args.command == 'publish' else prepare(args.target, config, base))
                if pub is None:
                    return
                if args.command == 'validate':
                    text = pub.text + f'\n\nAttachments ({len(pub.names)}):\n' + '\n'.join(pub.names)
                    if ui:
                        ui.document('Folder is valid', text)
                    else:
                        print(text)
                else:
                    from .browser import publish
                    publish(pub, config, base, ui)
    except (Exception, KeyboardInterrupt) as exc:
        message = str(exc) or 'Cancelled.'
        message += '\n\nIf an attempt is pending, inspect Classroom. Choosing Publish again will open recovery for this folder.'
        if ui:
            ui.error(message)
        elif args.gui:
            # Tk itself can fail; avoid claiming the error was displayed.
            if sys.platform == 'win32':
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, message, 'Classroom Publisher', 0x10)
            elif sys.stderr:
                print(message, file=sys.stderr)
        else:
            print(message, file=sys.stderr)
        raise SystemExit(1)
    finally:
        if ui:
            ui.close()


if __name__ == '__main__':
    main()
