import tempfile
import unittest
from pathlib import Path
from classroom_publisher.config import class_id
from classroom_publisher.integration import windows_command
from classroom_publisher.locking import single_instance


class SafetyTests(unittest.TestCase):
    def test_class_account_prefix(self):
        self.assertEqual(class_id('https://classroom.google.com/u/2/c/abc'), 'abc')
        with self.assertRaises(ValueError):
            class_id('https://classroom.google.com.evil.example/c/abc')

    def test_context_command_quotes_spaces_and_no_shell(self):
        command = windows_command(r'C:\My App\pythonw.exe', r'C:\My App\config.json', '%1')
        self.assertEqual(command, '"C:\\My App\\pythonw.exe" -m classroom_publisher.cli publish "%1" --config "C:\\My App\\config.json" --gui')
        self.assertNotIn('cmd.exe', command)

    def test_os_lock_prevents_concurrent_publication_and_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'lock'
            with single_instance(path):
                with self.assertRaisesRegex(ValueError, 'already running'):
                    with single_instance(path):
                        pass
            with single_instance(path):
                pass
