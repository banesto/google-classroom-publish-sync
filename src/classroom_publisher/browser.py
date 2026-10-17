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
    'open_composer': {'text_regex': r'^(?:Share something with your class|Announce something to your class|New announcement|Jauns paziņojums)(?:…|\.{3})?$'},
    'composer': '[role="dialog"]:has([contenteditable="true"]), form:has([contenteditable="true"])',
    'editor': '[contenteditable="true"][role="textbox"]',
    'add': {'role': 'button', 'name': 'Add'},
    'drive_direct': {'role': 'button', 'name': 'Pievienot Google diska failu'},
    'drive': {'role': 'menuitem', 'name': 'Google Drive'},
    'post': {'role': 'button', 'names': ['Post', 'Izlikt']},
    'picker_frame': 'iframe[src*="docs.google.com/picker"], iframe[src*="drive.google.com/picker"]',
    'picker_my_drive': {'role': 'tab', 'names': ['My Drive', 'Mans disks']},
    'picker_rows': '[role="row"], [role="option"][data-target="doc"]',
    'picker_breadcrumbs': '[aria-label="Breadcrumb"] button, [aria-label="Breadcrumb"] [role="button"], [role="button"][data-id][data-tooltiptext]',
    'picker_file_id_attribute': 'data-id',
    'picker_select': {'role': 'button', 'text_regex': r'^(?:Insert|Pievienot)$'},
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
        if 'text_regex' in spec:
            return scope.get_by_role(spec['role']).filter(has_text=re.compile(spec['text_regex']))
        if 'names' in spec:
            pattern = re.compile('^(?:' + '|'.join(re.escape(name) for name in spec['names']) + ')$')
            return scope.get_by_role(spec['role'], name=pattern)
        return scope.get_by_role(spec['role'], name=spec['name'], exact=True)
    if 'text_regex' in spec:
        return scope.get_by_text(re.compile(spec['text_regex']))
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
        # Older copies of ui.reference.json pinned the English-only default.
        # Migrate that exact legacy setting; preserve genuine custom selectors.
        if self.ui['picker_select'] == {'role': 'button', 'name': 'Insert'}:
            self.ui['picker_select'] = DEFAULT_UI['picker_select']
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

    def composer_opener(self):
        spec = self.ui['open_composer']
        # Classroom can expose the prompt as an accessible button name while
        # rendering different text inside it. Prefer that control when present.
        if isinstance(spec, dict) and 'text_regex' in spec:
            buttons = self.page.get_by_role('button', name=re.compile(spec['text_regex'])).filter(visible=True)
            if buttons.count():
                return unique(buttons, 'Open Stream composer')
        return unique(locate(self.page, spec).filter(visible=True), 'Open Stream composer')

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
        observed_names = [a['name'] for a in results]
        if observed_names != expected_names:
            if not results:
                reason = 'No Drive attachment links were recognized. The composer markup may differ from the configured selector.'
            elif sorted(observed_names) == sorted(expected_names):
                reason = 'All intended files were recognized, but their displayed order differs from natural filename order.'
            else:
                reason = 'The recognized attachment count or filenames differ from the intended files.'
            raise ValueError(reason + f'\nExpected ({len(expected_names)}): {expected_names!r}'
                             + f'\nRecognized ({len(observed_names)}): {observed_names!r}')
        if len({a['id'] for a in results}) != len(results):
            raise ValueError('The same Drive file is attached more than once.')
        return results

    def open_draft(self, pub):
        # Existing loaded posts with the same complete body are a possible duplicate.
        for post in locate(self.page, self.ui['posts']).all():
            if self.text_matches(post, pub.text):
                raise ValueError('A loaded Stream post already has this text. Inspect it before publishing.')
        self.wait(self.composer_opener,
                  'Cannot locate the Stream post box. This does not establish a permissions problem. '
                  'Open the class Stream and check its exact prompt/language against ui.open_composer; '
                  'if no post box is visible, check student posting permissions. Post was not clicked').click()
        composer = self.wait(lambda: self.composer(), 'Composer did not open')
        editor = unique(locate(composer, self.ui['editor']), 'Post editor')
        editor.fill(pub.text)
        self.attachments(composer, [])  # Refuse a restored draft with old attachments.

    def picker(self):
        frame = unique(self.page.locator(self.ui['picker_frame']).filter(visible=True), 'Drive picker frame')
        return frame.content_frame

    def breadcrumbs(self, picker, expected):
        controls = locate(picker, self.ui['picker_breadcrumbs']).filter(visible=True)
        names = [x.strip() for x in controls.all_inner_texts()]
        # Observed picker: root has no breadcrumbs; nested paths use English
        # "My Drive" even when the selected tab is Latvian "Mans disks".
        if not names and len(expected) == 1:
            tab = locate(picker, self.ui['picker_my_drive']).filter(visible=True)
            grid = picker.locator('[role="listbox"]:has([role="option"][data-target="doc"])').filter(visible=True)
            if tab.count() == 1 and tab.get_attribute('aria-selected') == 'true' and grid.count() == 1:
                return True
        roots = {'My Drive', expected[0]}
        if not names or names[0] not in roots or names[1:] != expected[1:]:
            raise ValueError('Drive folder breadcrumb differs from configured path: ' + ' / '.join(names))
        return True

    def exact_row(self, picker, name):
        rows = locate(picker, self.ui['picker_rows']).filter(has=picker.get_by_text(name, exact=True))
        return unique(rows, 'Drive item ' + name)

    def attach(self, pub):
        def attachment_control():
            composer = self.composer()
            direct_spec = self.ui.get('drive_direct')
            if direct_spec:
                direct = locate(composer, direct_spec).filter(visible=True)
                if direct.count():
                    return unique(direct, 'Direct Google Drive button'), True
            return unique(locate(composer, self.ui['add']).filter(visible=True), 'Add attachment'), False
        control, direct = self.wait(attachment_control, 'Cannot locate the Drive attachment control')
        control.click()
        if not direct:
            self.wait(lambda: unique(locate(self.page, self.ui['drive']), 'Google Drive menu option'),
                      'Google Drive menu did not appear').click()
        picker = self.wait(self.picker, 'Drive picker did not open')
        tab_spec = self.ui['picker_my_drive']
        tab = self.wait(lambda: unique(locate(picker, tab_spec).filter(visible=True), 'My Drive tab'),
                        'Drive picker contents did not load')
        # Use the matched localized name when checking the root breadcrumb.
        names = tab_spec.get('names', [tab_spec.get('name')])
        matched = [label for label in names if picker.get_by_role(
            tab_spec['role'], name=label, exact=True).filter(visible=True).count() == 1]
        if len(matched) != 1:
            raise ValueError('Cannot identify the My Drive breadcrumb name.')
        tab.click()
        path = matched
        # Reopening a picker may retain a nested folder. Explicitly return via
        # the observed root breadcrumb before accepting the root view.
        crumbs = locate(picker, self.ui['picker_breadcrumbs']).filter(visible=True)
        if crumbs.count() > 1:
            if crumbs.first.inner_text().strip() not in {'My Drive', matched[0]}:
                raise ValueError('Cannot identify the Drive root breadcrumb.')
            crumbs.first.click()
        self.wait(lambda: self.breadcrumbs(picker, path), 'Could not reset picker to My Drive')
        for folder in pub.drive_path:
            row = self.wait(lambda: self.exact_row(picker, folder), 'Missing or ambiguous Drive folder ' + folder)
            folder_id = row.get_attribute(self.ui['picker_file_id_attribute'])
            row.dblclick()
            path.append(folder)
            def verified_folder():
                self.breadcrumbs(picker, path)
                crumbs = locate(picker, self.ui['picker_breadcrumbs']).filter(visible=True)
                current_id = crumbs.last.get_attribute('data-id')
                if current_id is not None and (not folder_id or current_id != folder_id):
                    raise ValueError('Opened Drive folder ID differs from the selected folder.')
                return True
            self.wait(verified_folder, 'Could not verify Drive folder ' + folder)
        expected = []
        for name in pub.names:
            row = self.wait(lambda: self.exact_row(picker, name), 'Missing or ambiguous Drive file ' + name)
            file_id = row.get_attribute(self.ui['picker_file_id_attribute'])
            if not file_id or not re.fullmatch(r'[A-Za-z0-9_-]+', file_id):
                raise ValueError('Drive picker did not expose a verifiable file ID.')
            if file_id in [item['id'] for item in expected]:
                raise ValueError('The same Drive file is listed more than once.')
            row.click(modifiers=['ControlOrMeta'] if expected else [])
            expected.append({'name': name, 'id': file_id})
        def selection_matches():
            selected = locate(picker, self.ui['picker_rows']).filter(visible=True)
            ids = [item.get_attribute(self.ui['picker_file_id_attribute']) for item in selected.all()
                   if item.get_attribute('aria-selected') == 'true']
            if len(ids) != len(expected) or set(ids) != {item['id'] for item in expected}:
                raise ValueError('Picker selection differs from the intended Drive files.')
            return True
        self.wait(selection_matches, 'Could not verify the complete picker selection')
        # The observed button displays Pievienot but its accessible name also
        # includes the selected-item count. Match its visible text in the picker.
        try:
            confirmation = self.wait(lambda: unique(locate(picker, self.ui['picker_select']).filter(visible=True),
                                                   'Insert existing Drive file'),
                                     'Drive selection confirmation did not appear')
        except ValueError as exc:
            buttons = picker.get_by_role('button').filter(visible=True)
            observed = [{'text': button.inner_text().strip(), 'aria-label': button.get_attribute('aria-label')}
                        for button in buttons.all()]
            raise ValueError(f'{exc}\nEffective ui.picker_select: {self.ui["picker_select"]!r}'
                             f'\nVisible picker buttons: {observed!r}') from exc
        confirmation.click()
        self.page.locator(self.ui['picker_frame']).filter(visible=True).wait_for(state='hidden', timeout=self.timeout)
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
    expected = adapter.attach(pub)
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
    text = pub.text if pub.text_reviewed else ui.edit(pub)
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
