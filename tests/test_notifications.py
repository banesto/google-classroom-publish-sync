import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from classroom_publisher.browser import launch
from classroom_publisher.notifications import notify, WINDOWS_SCRIPT


class BackgroundTests(unittest.TestCase):
    def test_background_launch_and_visible_signin_override(self):
        with tempfile.TemporaryDirectory() as directory:
            playwright = Mock()
            profile = Path(directory) / 'child-profile'
            launch(playwright, profile, {})
            self.assertTrue(playwright.chromium.launch_persistent_context.call_args.kwargs['headless'])
            launch(playwright, profile, {}, headless=False)
            self.assertFalse(playwright.chromium.launch_persistent_context.call_args.kwargs['headless'])

    def test_windows_notification_keeps_text_out_of_script(self):
        title = 'Published'
        text = 'Child — Mājas darbs $(not-a-command) "quoted"'
        with patch('classroom_publisher.notifications.sys.platform', 'win32'), patch(
                'classroom_publisher.notifications.subprocess.Popen') as popen:
            self.assertTrue(notify(title, text))
            args, kwargs = popen.call_args
            self.assertEqual(json.loads(kwargs['env']['CLASSROOM_NOTIFICATION']), {'title': title, 'text': text})
            self.assertNotIn(text, WINDOWS_SCRIPT)
            self.assertNotIn(text, args[0])
            self.assertTrue(kwargs['creationflags'])

    def test_notification_unavailable_does_not_raise(self):
        with patch('classroom_publisher.notifications.sys.platform', 'darwin'), patch(
                'classroom_publisher.notifications.subprocess.Popen', side_effect=OSError('unavailable')):
            self.assertFalse(notify('Published', 'Child — Folder'))
