import json
import tempfile
import unittest
from pathlib import Path
from classroom_publisher.core import MARKER, PENDING, begin, confirm, prepare


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

    def test_wrong_root_and_date(self):
        self.config['classes'][0]['root'] = str(self.base / 'different')
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            self.prepare()
        self.folder.rename(self.folder.with_name('2026.02.30'))
        with self.assertRaises(ValueError):
            prepare(self.folder.with_name('2026.02.30'), self.config, self.base)

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
