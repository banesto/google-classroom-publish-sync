import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from classroom_publisher.cli import prepare_for_publish
from classroom_publisher.core import MARKER, PENDING, DRAFT, allow_retry, begin, confirm, prepare


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.folder = self.base / 'class' / 'Matemātika' / '2026.10.15'
        self.folder.mkdir(parents=True)
        self.config = {'children': {'one': {'email': 'one@example.com', 'profile': 'profile1'}},
                       'classes': [{'child': 'one', 'root': str(self.base / 'class'),
                                    'url': 'https://classroom.google.com/c/test', 'drive_path': ['class']}]}
        for name in ['10.jpg', '2.JPG']:
            (self.folder / name).write_bytes(b'test')

    def prepare(self):
        return prepare(self.folder, self.config, self.base)

    def test_natural_sort_and_description(self):
        (self.folder / 'description.txt').write_text('Uzdevumi 35–40.', encoding='utf-8')
        pub = self.prepare()
        self.assertEqual(pub.names, ['2.JPG', '10.jpg'])
        self.assertEqual(pub.text, 'Matemātika — 2026.10.15\n\nUzdevumi 35–40.')

    def test_recovery_preserves_reviewed_text_for_new_attempt(self):
        pub = self.prepare()
        pub.text = 'Edited title\n\nMy previously entered description.'
        begin(pub)
        allow_retry(self.folder)
        self.assertFalse((self.folder / PENDING).exists())
        self.assertTrue((self.folder / DRAFT).exists())
        retry = self.prepare()
        self.assertEqual(retry.text, pub.text)
        begin(retry)
        with self.assertRaisesRegex(ValueError, 'Unresolved attempt'):
            self.prepare()

    def test_recovered_draft_does_not_skip_attachment_validation(self):
        begin(self.prepare())
        allow_retry(self.folder)
        for i in range(19):
            (self.folder / f'extra{i}.jpg').write_bytes(b'test')
        with self.assertRaisesRegex(ValueError, 'maximum 20'):
            self.prepare()

    def test_publish_opens_recovery_and_reuses_saved_text(self):
        pub = self.prepare()
        pub.text = 'Saved title and description'
        begin(pub)
        ui = Mock()
        def recover(folder):
            allow_retry(folder)
            return True
        ui.recover.side_effect = recover
        retry = prepare_for_publish(self.folder, self.config, self.base, ui)
        self.assertEqual(retry.text, pub.text)
        ui.recover.assert_called_once_with(self.folder.resolve())

    def test_cancelled_inline_recovery_stops_publication(self):
        begin(self.prepare())
        ui = Mock()
        ui.recover.return_value = False
        self.assertIsNone(prepare_for_publish(self.folder, self.config, self.base, ui))
        self.assertTrue((self.folder / PENDING).exists())

    def test_verified_inline_recovery_does_not_republish(self):
        begin(self.prepare())
        ui = Mock()
        def recover(folder):
            confirm(folder)
            return False
        ui.recover.side_effect = recover
        self.assertIsNone(prepare_for_publish(self.folder, self.config, self.base, ui))
        self.assertTrue((self.folder / MARKER).exists())

    def test_normal_publish_does_not_open_recovery(self):
        ui = Mock()
        self.assertIsNotNone(prepare_for_publish(self.folder, self.config, self.base, ui))
        ui.recover.assert_not_called()

    def test_limit_blocks_without_markers(self):
        for i in range(19):
            (self.folder / f'z{i}.pdf').write_bytes(b'test')
        with self.assertRaisesRegex(ValueError, 'z18.pdf'):
            self.prepare()
        self.assertFalse((self.folder / MARKER).exists())
        self.assertFalse((self.folder / PENDING).exists())

    def test_exactly_twenty(self):
        for i in range(18):
            (self.folder / f'z{i}.pdf').write_bytes(b'test')
        self.assertEqual(len(self.prepare().names), 20)

    def test_uncertain_attempt_blocks_retry(self):
        pub = self.prepare()
        begin(pub)
        with self.assertRaisesRegex(ValueError, 'Unresolved'):
            self.prepare()
        with self.assertRaises(FileExistsError):
            begin(pub)
        self.assertFalse((self.folder / MARKER).exists())

    def test_success_has_full_text_and_blocks_retry(self):
        pub = self.prepare()
        pub.text += '\n\nEdited text'
        begin(pub)
        confirm(self.folder, 'https://classroom.google.com/c/test/p/post')
        marker = (self.folder / MARKER).read_text(encoding='utf-8')
        self.assertIn(pub.text, marker)
        self.assertIn('Attachment count: 2', marker)
        self.assertIn('2.JPG\n10.jpg', marker)
        self.assertFalse((self.folder / PENDING).exists())
        with self.assertRaisesRegex(ValueError, 'Already published'):
            self.prepare()

    def test_wrong_root(self):
        self.config['classes'][0]['root'] = str(self.base / 'different')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.prepare()

    def test_any_folder_name_and_depth(self):
        target = self.base / 'class' / 'Projects' / 'Term 1' / 'Finished exercises'
        target.parent.mkdir(parents=True)
        self.folder.rename(target)
        pub = prepare(target, self.config, self.base)
        self.assertEqual(pub.text, 'Projects — Term 1 — Finished exercises')
        self.assertEqual(pub.drive_path, ['class', 'Projects', 'Term 1', 'Finished exercises'])

    def test_direct_child_and_root_itself(self):
        root = self.base / 'class'
        target = root / 'Homework'
        self.folder.rename(target)
        pub = prepare(target, self.config, self.base)
        self.assertEqual(pub.text, 'Homework')
        self.assertEqual(pub.drive_path, ['class', 'Homework'])
        (root / 'root.jpg').write_bytes(b'test')
        pub = prepare(root, self.config, self.base)
        self.assertEqual(pub.text, 'class')
        self.assertEqual(pub.drive_path, ['class'])
        self.assertEqual(pub.names, ['root.jpg'])  # Never recurse into Homework.

    def test_overlapping_roots_rejected_for_selected_folder(self):
        self.config['classes'].append(dict(self.config['classes'][0],
            root=str(self.folder.parent), drive_path=['class', 'Matemātika']))
        with self.assertRaisesRegex(ValueError, 'overlapping roots'):
            self.prepare()

    def test_symlink_cannot_escape_configured_root(self):
        outside = self.base / 'outside'
        outside.mkdir()
        (outside / 'image.jpg').write_bytes(b'test')
        link = self.base / 'class' / 'linked'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('Creating directory symlinks is not allowed on this host.')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            prepare(link, self.config, self.base)

    def test_empty_and_unsupported(self):
        for p in self.folder.iterdir():
            p.unlink()
        (self.folder / 'notes.txt').write_bytes(b'test')
        with self.assertRaisesRegex(ValueError, 'No supported'):
            self.prepare()

    def test_profiles_must_be_unique(self):
        self.config['children']['two'] = dict(self.config['children']['one'], email='two@example.com')
        with self.assertRaisesRegex(ValueError, 'different browser profile'):
            self.prepare()

    def test_invalid_confirmation_leaves_pending(self):
        begin(self.prepare())
        with self.assertRaises(ValueError):
            confirm(self.folder, 'https://example.com')
        self.assertTrue((self.folder / PENDING).exists())
        self.assertFalse((self.folder / MARKER).exists())


if __name__ == '__main__':
    unittest.main()
