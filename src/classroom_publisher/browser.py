"""Browser-only adapter. Never reads attachment bytes or submits an upload form.

UI selectors are deliberately configurable: Google provides no stable DOM contract.
An unrecognized or ambiguous UI stops the attempt; no broad click fallbacks are used.
"""
import re
import time
from urllib.parse import parse_qs, urlparse
from .config import class_id, profile_path
from .core import begin, confirm, recheck, update_pending

DEFAULT_UI = {
    'account': ('a[href^="https://accounts.google.com/SignOutOptions"], '
                '[aria-label*="Google Account"], [data-tooltip*="Google Account"]'),
    'open_composer': {'text': 'Announce something to your class'},
    'composer': '[role="dialog"]:has([contenteditable="true"]), form:has([contenteditable="true"])',
    'editor': '[contenteditable="true"][role="textbox"]',
    'add': {'role': 'button', 'name': 'Add'},
    'drive': {'role': 'menuitem', 'name': 'Google Drive'},
    'post': {'role': 'button', 'name': 'Post'},
    'picker_frame': 'iframe[src*="docs.google.com/picker"], iframe[src*="drive.google.com/picker"]',
    'picker_my_drive': {'role': 'tab', 'name': 'My Drive'},
    'picker_rows': '[role="row"]',
    'picker_breadcrumbs': '[aria-label="Breadcrumb"] button, [aria-label="Breadcrumb"] [role="button"]',
    'picker_file_id_attribute': 'data-id',
    'picker_select': {'role': 'button', 'name': 'Insert'},
    'attachments': 'a[href*="drive.google.com/file/d/"], a[href*="drive.google.com/open?"]',
    'posts': '[data-stream-item-id]',
    'post_id_attribute': 'data-stream-item-id',
    'post_link': 'a[href*="/p/"]',
}


def normalized_text(text):
    # Compare rendered whitespace, retaining the exact reviewed text in the marker.
    return ' '.join((text or '').split())


def locate(scope, spec):
    if isinstance(spec, str):
        return scope.locator(spec)
    if 'role' in spec:
        return scope.get_by_role(spec['role'], name=spec['name'], exact=True)
    return scope.get_by_text(spec['text'], exact=True)


def unique(locator, label):
    if locator.count() != 1:
        raise ValueError(f'{label}: expected one match, found {locator.count()}. Stop and inspect UI settings.')
    return locator


def drive_id(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.netloc != 'drive.google.com':
        raise ValueError('Attachment is not an existing Google Drive link.')
    match = re.fullmatch(r'/file/d/([A-Za-z0-9_-]+)(?:/.*)?', p.path)
    value = match[1] if match else parse_qs(p.query).get('id', [''])[0] if p.path == '/open' else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Cannot identify the existing Drive attachment.')
    return value


class ClassroomPage:
    def __init__(self, page, config, status=lambda _: None):
        self.page = page
        self.ui = dict(DEFAULT_UI, **config.get('ui', {}))
        self.timeout = config.get('timeout_ms', 20000)
        self.page.set_default_timeout(self.timeout)
        self.status = status

    def wait(self, check, label):
        deadline = time.monotonic() + self.timeout / 1000
        last = None
        while time.monotonic() < deadline:
            try:
                result = check()
                if result:
                    return result
            except (ValueError, AssertionError) as exc:
                last = exc
            self.page.wait_for_timeout(150)
        raise ValueError(f'{label}. {last or "Expected page state did not appear."}')

    def identity(self, pub):
        if class_id(self.page.url) != class_id(pub.url):
            raise ValueError('The browser is in the wrong class.')
        # Google localizes the account label. The account-menu URL identifies
        # the control independently of language; never search the whole page
        # for the desired email (it could belong to a classmate or another login).
        controls = locate(self.page, self.ui['account']).filter(visible=True)
        if controls.count() != 1:
            raise ValueError(
                'Cannot identify the active Google account control '
                f'({controls.count()} visible matches). Your login may be valid. '
                'The account indicator may still be loading, or ui.account needs '
                'adjusting for this Classroom layout. No publication is allowed '
                'until the active email can be verified.')
        account = controls
        value = ' '.join([account.get_attribute(attr) or ''
                          for attr in ('aria-label', 'title', 'data-tooltip')]
                         + [account.inner_text()])
        emails = set(re.findall(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', value.casefold()))
        if not emails:
            raise ValueError('The Google account control is visible, but it does not expose an email. '
                             'Inspect its label/tooltip before changing ui.account; '
                             'the configured email alone is not proof of the active login.')
        if emails != {pub.email.casefold()}:
            raise ValueError('Active Google account does not match ' + pub.email + '. Use Sign in for this child.')
        return True

    def composer(self):
        return unique(locate(self.page, self.ui['composer']), 'Post composer')

    def post_ids(self):
        ids = []
        for item in locate(self.page, self.ui['posts']).all():
            value = item.get_attribute(self.ui['post_id_attribute'])
            if not value or value in ids:
                raise ValueError('Stream items need unique stable IDs; inspect UI settings.')
            ids.append(value)
        return ids

    def text_matches(self, post, text):
        if self.ui.get('post_text'):
            body = unique(locate(post, self.ui['post_text']), 'Published post text')
            return normalized_text(body.inner_text()) == normalized_text(text)
        # Playwright exact text matching normalizes rendered whitespace.
        return post.get_by_text(normalized_text(text), exact=True).count() == 1

    def attachments(self, scope, expected_names):
        results = []
        for link in locate(scope, self.ui['attachments']).all():
            candidates = [link.get_attribute('title') or '', link.get_attribute('aria-label') or '']
            candidates += link.inner_text().splitlines()
            names = {name for name in expected_names if name in [c.strip() for c in candidates]
                     or link.get_by_text(name, exact=True).count() == 1}
            if len(names) != 1:
                raise ValueError('Cannot uniquely identify an attachment filename; inspect UI settings.')
            results.append({'name': names.pop(), 'id': drive_id(link.get_attribute('href') or '')})
        if [a['name'] for a in results] != expected_names:
            raise ValueError('Attachment count or displayed order differs from the natural filename order.')
        if len({a['id'] for a in results}) != len(results):
            raise ValueError('The same Drive file is attached more than once.')
        return results

    def open_draft(self, pub):
        # Existing loaded posts with the same complete body are a possible duplicate.
        for post in locate(self.page, self.ui['posts']).all():
            if self.text_matches(post, pub.text):
                raise ValueError('A loaded Stream post already has this text. Inspect it before publishing.')
        self.wait(lambda: unique(locate(self.page, self.ui['open_composer']), 'Open Stream composer'),
                  'Stream composer is unavailable; check student posting permissions').click()
        composer = self.wait(lambda: self.composer(), 'Composer did not open')
        editor = unique(locate(composer, self.ui['editor']), 'Post editor')
        editor.fill(pub.text)
        self.attachments(composer, [])  # Refuse a restored draft with old attachments.

    def picker(self):
        frame = unique(self.page.locator(self.ui['picker_frame']).filter(visible=True), 'Drive picker frame')
        return frame.content_frame

    def breadcrumbs(self, picker, expected):
        names = [x.strip() for x in locate(picker, self.ui['picker_breadcrumbs']).all_inner_texts()]
        if names != expected:
            raise ValueError('Drive folder breadcrumb differs from configured path: ' + ' / '.join(names))
        return True

    def exact_row(self, picker, name):
        rows = locate(picker, self.ui['picker_rows']).filter(has=picker.get_by_text(name, exact=True))
        return unique(rows, 'Drive item ' + name)

    def attach(self, pub, name, expected):
        self.status('Selecting existing Drive file: ' + name)
        unique(locate(self.composer(), self.ui['add']), 'Add attachment').click()
        self.wait(lambda: unique(locate(self.page, self.ui['drive']), 'Google Drive menu option'),
                  'Google Drive menu did not appear').click()
        picker = self.wait(self.picker, 'Drive picker did not open')
        self.wait(lambda: unique(locate(picker, self.ui['picker_my_drive']), 'My Drive tab'),
                  'Drive picker contents did not load').click()
        path = [self.ui['picker_my_drive']['name']]
        self.wait(lambda: self.breadcrumbs(picker, path), 'Could not reset picker to My Drive')
        for folder in pub.drive_path:
            row = self.wait(lambda: self.exact_row(picker, folder), 'Missing or ambiguous Drive folder ' + folder)
            row.dblclick()
            path.append(folder)
            self.wait(lambda: self.breadcrumbs(picker, path), 'Could not verify Drive folder ' + folder)
        row = self.wait(lambda: self.exact_row(picker, name), 'Missing or ambiguous Drive file ' + name)
        file_id = row.get_attribute(self.ui['picker_file_id_attribute'])
        if not file_id or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
            raise ValueError('Drive picker did not expose a verifiable file ID. No upload or Copy fallback is allowed.')
        row.click()
        unique(locate(picker, self.ui['picker_select']), 'Insert existing Drive file').click()
        self.page.locator(self.ui['picker_frame']).filter(visible=True).wait_for(state='hidden', timeout=self.timeout)
        expected = expected + [{'name': name, 'id': file_id}]
        def verified():
            actual = self.attachments(self.composer(), [a['name'] for a in expected])
            if actual != expected:
                raise ValueError('Draft Drive file IDs differ from the selected existing files. Stopping.')
            return actual
        return self.wait(verified, 'Drive attachments did not match the selection')

    def draft_matches(self, pub, expected):
        self.identity(pub)
        editor = unique(locate(self.composer(), self.ui['editor']), 'Post editor')
        if normalized_text(editor.inner_text()) != normalized_text(pub.text):
            raise ValueError('Browser text differs from the reviewed text.')
        if self.attachments(self.composer(), pub.names) != expected:
            raise ValueError('Draft attachment identities changed.')

    def find_published(self, pub, expected, baseline):
        matches = []
        for post in locate(self.page, self.ui['posts']).all():
            post_id = post.get_attribute(self.ui['post_id_attribute'])
            if post_id and post_id not in baseline and self.text_matches(post, pub.text):
                if self.attachments(post, pub.names) == expected:
                    matches.append((post_id, post))
        if len(matches) != 1:
            raise ValueError('Cannot uniquely confirm a new post with the complete text and all Drive attachments.')
        return matches[0]

    def post_once(self, pub, expected, baseline):
        self.draft_matches(pub, expected)
        recheck(pub)
        button = unique(locate(self.composer(), self.ui['post']), 'Post button')
        if not button.is_enabled():
            raise ValueError('Post button is disabled.')
        update_pending(pub.folder, stage='posting', attachments=expected, baseline_post_ids=baseline)
        self.status('Publishing once; waiting for confirmation…')
        button.click(timeout=self.timeout)  # Never retry this mutation, including on timeout.
        post_id, _ = self.wait(lambda: self.find_published(pub, expected, baseline), 'Post outcome is uncertain')
        update_pending(pub.folder, stage='verifying', observed_post_id=post_id)
        self.page.reload(wait_until='domcontentloaded')
        self.wait(lambda: self.identity(pub), 'Cannot verify the active account after reload')
        confirmed_id, post = self.wait(lambda: self.find_published(pub, expected, baseline),
                                       'The post could not be verified after reload')
        if confirmed_id != post_id:
            raise ValueError('Persisted post identity changed. Outcome remains uncertain.')
        links = locate(post, self.ui['post_link'])
        url = ''
        if links.count() == 1:
            candidate = links.get_attribute('href') or ''
            from urllib.parse import urljoin
            candidate = urljoin(self.page.url, candidate)
            try:
                if class_id(candidate) == class_id(pub.url):
                    url = candidate
            except ValueError:
                pass  # Post URL is optional; never fabricate one from a Stream ID.
        confirm(pub.folder, url, 'browser verified new stable post ID, text and ordered Drive IDs after reload')
        return post_id


def run_publication(page, pub, config, review_draft, status=lambda _: None):
    """Shared by the real browser and isolated browser-fixture integration tests."""
    adapter = ClassroomPage(page, config, status)
    page.goto(pub.url, wait_until='domcontentloaded')
    adapter.wait(lambda: adapter.identity(pub), 'Check the child login and account selector')
    baseline = adapter.post_ids()
    adapter.open_draft(pub)
    expected = []
    for name in pub.names:
        expected = adapter.attach(pub, name, expected)
    update_pending(pub.folder, stage='draft_ready', attachments=expected, baseline_post_ids=baseline)
    adapter.draft_matches(pub, expected)
    if not review_draft(pub):
        return False  # Keep pending: a human may have interacted with the visible browser.
    adapter.post_once(pub, expected, baseline)
    return True


def launch(p, profile, config):
    profile.mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(str(profile), channel=config.get('browser_channel', 'chrome'),
                                               headless=False, accept_downloads=False)


def publish(pub, config, config_dir, ui):
    from playwright.sync_api import sync_playwright
    text = ui.edit(pub)
    if text is None:
        return False
    pub.text = text
    recheck(pub)
    begin(pub)
    with sync_playwright() as p:
        context = launch(p, pub.profile, config)
        try:
            page = context.new_page()
            result = run_publication(page, pub, config, ui.review_draft, ui.status)
            if result:
                ui.info('Published', 'The post was verified after reload. classroom-published.txt is saved.')
            else:
                ui.info('Stopped', 'No automated Post click was made. Use Recover to inspect and clear this attempt.')
            return result
        finally:
            context.close()


def sign_in(child, config, base, ui, inspect=False):
    from playwright.sync_api import sync_playwright
    target = next(c['url'] for c in config['classes'] if c['child'] == child)
    with sync_playwright() as p:
        context = launch(p, profile_path(child, config, base), config)
        try:
            page = context.new_page()
            page.goto(target, wait_until='domcontentloaded')
            ui.info('Sign in: ' + config['children'][child]['email'],
                    'Sign in in the Chrome window using this child’s account.\n'
                    'Open the configured class Stream, then click OK here.\n'
                    'Do not publish during setup. The saved login works when Chrome is closed.')
            if inspect:
                page.pause()
            # Verify login against the configured account; no publish or pending files.
            from types import SimpleNamespace
            adapter = ClassroomPage(page, config)
            adapter.wait(lambda: adapter.identity(SimpleNamespace(
                url=target, email=config['children'][child]['email'])),
                'Could not verify the signed-in account')
            ui.info('Login saved', 'This child’s dedicated browser profile is ready.')
        finally:
            context.close()
