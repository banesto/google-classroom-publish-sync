"""Full publication flow against a local fake Classroom/Drive UI.

Every network request is intercepted. No Google service is contacted.
Enable with CLASSROOM_BROWSER_TESTS=1 and installed Chrome.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from classroom_publisher.browser import ClassroomPage, run_publication, verify_existing_page
from classroom_publisher.core import MARKER, PENDING, begin, prepare, update_pending

CLASSROOM = r'''<!doctype html><html><head><meta charset="utf-8"></head><body>
<a aria-label="Google Account: Child (ACCOUNT)">Account</a>
<button id="open">Announce something to your class</button>
<div id="composer" role="dialog" hidden>
<div contenteditable="true" role="textbox"></div>
<button id="add">Add</button>
<button role="menuitem" id="drive" hidden>Google Drive</button>
<section id="attachments"></section><button id="post">Post</button></div>
<section id="stream"></section>
<script>
const saved = SAVED;
let selected=[];
function render(post) {
 let article=document.createElement('article'); article.dataset.streamItemId=post.id;
 let body=document.createElement('p'); body.textContent=post.text; article.append(body);
 for (let f of post.files) {
  let a=document.createElement('a'); a.href='https://drive.google.com/file/d/'+f.id+'/view';
  a.textContent=f.name; article.append(a);
 }
 let a=document.createElement('a'); a.href='/c/test/p/'+post.id; a.textContent='Post link'; article.append(a);
 document.querySelector('#stream').append(article);
}
saved.forEach(render);
document.querySelector('#open').onclick=()=>document.querySelector('#composer').hidden=false;
document.querySelector('#add').onclick=()=>document.querySelector('#drive').hidden=false;
document.querySelector('#drive').onclick=()=> {
 document.querySelector('#drive').hidden=true;
 let frame=document.createElement('iframe'); frame.src='https://docs.google.com/picker'; document.body.append(frame);
};
window.addEventListener('message', event=> {
 if (!event.data.files) return;
 selected.push(...event.data.files);
 document.querySelector('iframe').remove();
 let files=REORDER ? [...selected].reverse() : selected;
 document.querySelector('#attachments').innerHTML='';
 for (let f of files) {
  let a=document.createElement('a'); a.href='https://drive.google.com/file/d/'+f.id+'/view';
  a.textContent=f.name; document.querySelector('#attachments').append(a);
 }
});
document.querySelector('#post').onclick=async()=> {
 let result=await fetch('/fixture/publish',{method:'POST',body:JSON.stringify({
  text:document.querySelector('[contenteditable]').innerText, files:selected
 })});
 if (result.ok) { let post=await result.json(); document.querySelector('#composer').hidden=true; render(post); }
};
</script></body></html>'''

PICKER = r'''<!doctype html><html><head><meta charset="utf-8"></head><body>
<button role="tab" id="mydrive">My Drive</button>
<nav aria-label="Breadcrumb"></nav><div id="rows"></div><button id="insert">Insert</button>
<script>
const path=FOLDERPATH;
const files=FILES;
let depth=0, chosen=[];
function render(){
 let nav=document.querySelector('nav'); nav.innerHTML='';
 for(let name of ['My Drive',...path.slice(0,depth)]) {
  let b=document.createElement('button'); b.textContent=name; nav.append(b);
 }
 let container=document.querySelector('#rows'); container.innerHTML='';
 let items=depth<path.length ? [{name:path[depth],id:'folder'+depth}] : files;
 for(let item of items){
  let row=document.createElement('div'); row.setAttribute('role','row'); row.dataset.id=item.id;
  let label=document.createElement('span'); label.textContent=item.name; row.append(label);
  row.ondblclick=()=>{if(depth<path.length){depth++;render();}};
  row.onclick=(event)=>{
   if (!event.ctrlKey && !event.metaKey) {
    chosen=[]; container.querySelectorAll('[aria-selected]').forEach(el=>el.setAttribute('aria-selected','false'));
   }
   chosen.push(item); row.setAttribute('aria-selected','true');
   document.querySelector('#insert').setAttribute('aria-label', 'Pievienot '+chosen.length+' vienumi');
 }; container.append(row);
 }
}
document.querySelector('#mydrive').onclick=()=>{depth=0;render();};
document.querySelector('#insert').onclick=()=>{if(chosen.length)parent.postMessage({files:chosen},'*');};
render();
</script></body></html>'''


@unittest.skipUnless(os.environ.get('CLASSROOM_BROWSER_TESTS') == '1', 'Set CLASSROOM_BROWSER_TESTS=1 for local Chrome integration tests')
class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright
        cls.playwright = sync_playwright().start()
        cls.tmp_profile = tempfile.TemporaryDirectory()
        cls.browser = cls.playwright.chromium.launch_persistent_context(cls.tmp_profile.name, channel='chrome', headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.tmp_profile.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.folder = base / 'class' / 'Matemātika' / '2026.10.15'
        self.folder.mkdir(parents=True)
        for name in ['10.jpg', '2.jpg']:
            (self.folder / name).write_bytes(b'local test file; never uploaded')
        self.config = {'children': {'one': {'email': 'child@example.com', 'profile': str(base / 'profile')}},
                       'classes': [{'child': 'one', 'root': str(base / 'class'), 'drive_path': ['class'],
                                    'url': 'https://classroom.google.com/c/test'}], 'timeout_ms': 1200}
        self.pub = prepare(self.folder, self.config, base)
        self.pub.text += '\n\nIzpildīti uzdevumi 35–40.'
        begin(self.pub)
        self.posts = []
        self.post_calls = 0
        self.picker_visits = 0
        self.account = 'child@example.com'
        self.files = [{'name': '2.jpg', 'id': 'drive2'}, {'name': '10.jpg', 'id': 'drive10'}]
        self.reorder = False
        self.persist = True
        self.fail_click_response = False
        self.reload_mutation = False
        self.latvian_direct = False
        self.grid_picker = False
        self.delayed_selection = False
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.page.route('**/*', self.route)

    def route(self, route):
        url = route.request.url
        if url == 'https://docs.google.com/picker':
            self.picker_visits += 1
            picker_html = PICKER.replace('My Drive', 'Mans disks') if self.latvian_direct else PICKER
            if self.grid_picker:
                picker_html = picker_html.replace('<button id="insert">Insert</button>',
                    '<button id="insert" aria-label="Pievienot 1 vienumu"><span>Pievienot</span></button>')
                picker_html = picker_html.replace('id="mydrive"', 'id="mydrive" aria-selected="true"')
                picker_html = picker_html.replace('<nav aria-label="Breadcrumb">', '<nav>')
                picker_html = picker_html.replace('<div id="rows">', '<div id="rows" role="listbox">')
                picker_html = picker_html.replace("['Mans disks',...path.slice(0,depth)]", "(depth ? ['My Drive',...path.slice(0,depth)] : [])")
                picker_html = picker_html.replace("b.textContent=name; nav.append(b);", """b.textContent=name;
                    b.setAttribute('role', 'button'); b.dataset.tooltiptext=name;
                    b.dataset.id=nav.children.length ? 'folder'+(nav.children.length-1) : 'root';
                    nav.append(b);""")
                picker_html = picker_html.replace("row.setAttribute('role','row');", "row.setAttribute('role','option'); row.dataset.target='doc';")
            if self.delayed_selection:
                picker_html = picker_html.replace('row.onclick=(event)=>{', 'row.onclick=(event)=>{ setTimeout(()=>{').replace('}; container.append(row);', '}, 180); }; container.append(row);')
            route.fulfill(content_type='text/html', body=picker_html.replace('FILES', json.dumps(self.files))
                          .replace('FOLDERPATH', json.dumps(self.pub.drive_path)))
        elif url.endswith('/fixture/publish'):
            self.post_calls += 1
            post = dict(json.loads(route.request.post_data), id='new-post')
            if self.persist:
                self.posts.append(post)
            if self.fail_click_response:
                route.abort()
            else:
                route.fulfill(content_type='application/json', body=json.dumps(post))
        elif url == 'https://classroom.google.com/c/test':
            posts = json.loads(json.dumps(self.posts))
            if self.reload_mutation and posts:
                posts[-1]['files'][-1]['id'] = 'wrong-drive-id'
            html = CLASSROOM.replace('ACCOUNT', self.account).replace('SAVED', json.dumps(posts))
            if self.latvian_direct:
                html = html.replace('<button id="add">Add</button>',
                                    '<button id="add" hidden>Add</button>')
                html = html.replace('<button role="menuitem" id="drive" hidden>Google Drive</button>',
                                    '<button id="drive" aria-label="Pievienot Google diska failu"><svg></svg></button>')
                html = html.replace('id="post">Post', 'id="post">Izlikt')
                html = html.replace("document.querySelector('#drive').hidden=true;", '')
            route.fulfill(content_type='text/html', body=html.replace('REORDER', str(self.reorder).lower()))
        else:
            route.abort()  # Fixture cannot reach real Google or download anything.

    def run_flow(self):
        return run_publication(self.page, self.pub, self.config)

    def account_page(self):
        self.page.goto(self.pub.url)
        return self.page.locator('a[aria-label]')

    def test_student_composer_prompt_variants(self):
        for prompt in ('Share something with your class', 'Share something with your class...',
                       'Share something with your class…', 'Announce something to your class',
                       'New announcement', 'Jauns paziņojums'):
            with self.subTest(prompt=prompt):
                self.page.goto(self.pub.url)
                self.page.locator('#open').evaluate('(el, text) => el.textContent = text', prompt)
                ClassroomPage(self.page, self.config).open_draft(self.pub)
                self.assertEqual(self.page.locator('[contenteditable]').inner_text().split(), self.pub.text.split())
                self.assertEqual(self.post_calls, 0)

    def test_ambiguous_composer_stops_before_post(self):
        self.page.goto(self.pub.url)
        self.page.locator('#open').evaluate('el => el.after(el.cloneNode(true))')
        with self.assertRaisesRegex(ValueError, 'expected one match, found 2'):
            ClassroomPage(self.page, self.config).open_draft(self.pub)
        self.assert_blocked(0)

    def test_composer_accessible_button_label(self):
        for label in ('New announcement', 'Jauns paziņojums'):
            with self.subTest(label=label):
                self.page.goto(self.pub.url)
                self.page.locator('#open').evaluate('''(el, label) => {
                    el.textContent = 'A different visible prompt';
                    el.setAttribute('aria-label', label);
                }''', label)
                ClassroomPage(self.page, self.config).open_draft(self.pub)
                self.assertTrue(self.page.locator('#composer').is_visible())
                self.assertEqual(self.post_calls, 0)

    def test_localized_composer_override(self):
        self.page.goto(self.pub.url)
        self.page.locator('#open').evaluate('(el) => el.textContent = "Class post prompt in another language"')
        config = dict(self.config, ui={'open_composer': {'text': 'Class post prompt in another language'}})
        ClassroomPage(self.page, config).open_draft(self.pub)
        self.assertEqual(self.post_calls, 0)

    def test_localized_account_label_with_menu_link(self):
        account = self.account_page()
        account.evaluate('''el => {
            el.setAttribute('aria-label', 'Google konts: Bērns (child@example.com)');
            el.setAttribute('href', 'https://accounts.google.com/SignOutOptions?hl=lv');
        }''')
        self.assertTrue(ClassroomPage(self.page, self.config).identity(self.pub))

    def test_account_email_in_tooltip(self):
        account = self.account_page()
        account.evaluate('''el => {
            el.removeAttribute('aria-label');
            el.setAttribute('href', 'https://accounts.google.com/SignOutOptions');
            el.setAttribute('data-tooltip', 'Google konts: child@example.com');
        }''')
        self.assertTrue(ClassroomPage(self.page, self.config).identity(self.pub))

    def test_hidden_duplicate_account_control_ignored(self):
        account = self.account_page()
        account.evaluate('''el => {
            const copy = el.cloneNode(true); copy.hidden = true; el.after(copy);
        }''')
        self.assertTrue(ClassroomPage(self.page, self.config).identity(self.pub))

    def test_multiple_visible_account_controls_rejected(self):
        account = self.account_page()
        account.evaluate('el => el.after(el.cloneNode(true))')
        with self.assertRaisesRegex(ValueError, '2 visible matches'):
            ClassroomPage(self.page, self.config).identity(self.pub)

    def test_email_elsewhere_is_not_identity_evidence(self):
        account = self.account_page()
        account.evaluate('''el => {
            el.remove(); const p = document.createElement('p');
            p.textContent = 'child@example.com'; document.body.append(p);
        }''')
        with self.assertRaisesRegex(ValueError, '0 visible matches'):
            ClassroomPage(self.page, self.config).identity(self.pub)

    def test_localized_wrong_account_still_rejected(self):
        account = self.account_page()
        account.evaluate('''el => {
            el.setAttribute('aria-label', 'Google konts: other@example.com');
            el.setAttribute('href', 'https://accounts.google.com/SignOutOptions');
        }''')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            ClassroomPage(self.page, self.config).identity(self.pub)

    def test_account_indicator_can_load_late(self):
        account = self.account_page()
        account.evaluate('''el => {
            const label = el.getAttribute('aria-label'); el.removeAttribute('aria-label');
            setTimeout(() => el.setAttribute('aria-label', label), 250);
        }''')
        adapter = ClassroomPage(self.page, self.config)
        self.assertTrue(adapter.wait(lambda: adapter.identity(self.pub), 'Account failed to load'))

    def assert_blocked(self, calls):
        self.assertTrue((self.folder / PENDING).exists())
        self.assertFalse((self.folder / MARKER).exists())
        self.assertEqual(self.post_calls, calls)

    def test_two_file_end_to_end_and_marker(self):
        self.assertTrue(self.run_flow())
        self.assertEqual(self.picker_visits, 1)
        self.assertEqual(self.post_calls, 1)
        self.assertEqual([a['id'] for a in self.posts[0]['files']], ['drive2', 'drive10'])
        marker = (self.folder / MARKER).read_text(encoding='utf-8')
        self.assertIn(self.pub.text, marker)
        self.assertIn('https://classroom.google.com/c/test/p/new-post', marker)
        self.assertFalse((self.folder / PENDING).exists())

    def test_latvian_direct_drive_folder_flow(self):
        self.latvian_direct = True
        self.pub.drive_path = ['5.klase', 'L_Lat.v', self.folder.name]
        self.assertTrue(self.run_flow())
        self.assertEqual(self.post_calls, 1)
        self.assertEqual([a['id'] for a in self.posts[0]['files']], ['drive2', 'drive10'])
        self.assertTrue((self.folder / MARKER).exists())

    def test_observed_grid_and_mixed_language_breadcrumbs(self):
        self.latvian_direct = True
        self.grid_picker = True
        self.pub.drive_path = ['5.klase', 'L_Lat.v', self.folder.name]
        self.assertTrue(self.run_flow())
        self.assertEqual(self.post_calls, 1)

    def test_legacy_insert_override_uses_observed_latvian_button(self):
        self.latvian_direct = True
        self.grid_picker = True
        self.config['ui'] = {'picker_select': {'role': 'button', 'name': 'Insert'}}
        self.assertTrue(self.run_flow())
        self.assertEqual(self.post_calls, 1)

    def test_missing_confirmation_reports_actual_buttons(self):
        self.config['ui'] = {'picker_select': {'role': 'button', 'name': 'Missing custom label'}}
        with self.assertRaisesRegex(ValueError, 'Visible picker buttons:.*Insert'):
            self.run_flow()
        self.assert_blocked(0)

    def test_grid_root_does_not_accept_missing_nested_breadcrumbs(self):
        self.page.goto(self.pub.url)
        self.page.locator('body').evaluate('''el => el.innerHTML =
            '<button role="tab" aria-selected="true">Mans disks</button>' +
            '<div role="listbox"><div role="option" data-target="doc">Folder</div></div>' ''')
        adapter = ClassroomPage(self.page, self.config)
        self.assertTrue(adapter.breadcrumbs(self.page, ['Mans disks']))
        with self.assertRaisesRegex(ValueError, 'breadcrumb differs'):
            adapter.breadcrumbs(self.page, ['Mans disks', '5.klase'])

    def test_duplicate_direct_drive_controls_rejected(self):
        self.latvian_direct = True
        self.page.goto(self.pub.url)
        adapter = ClassroomPage(self.page, self.config)
        adapter.open_draft(self.pub)
        self.page.locator('#drive').evaluate('el => el.after(el.cloneNode(true))')
        with self.assertRaisesRegex(ValueError, 'Direct Google Drive button: expected one match, found 2'):
            adapter.attach(self.pub)
        self.assert_blocked(0)

    def test_nested_non_date_folder_end_to_end(self):
        (self.folder / PENDING).unlink()  # No browser work has started in this fixture.
        target = Path(self.tmp.name) / 'class' / 'Projects' / 'Term 1' / 'Finished exercises'
        target.parent.mkdir(parents=True)
        self.folder.rename(target)
        self.folder = target
        self.pub = prepare(target, self.config, Path(self.tmp.name))
        begin(self.pub)
        self.assertTrue(self.run_flow())
        self.assertEqual(self.post_calls, 1)
        self.assertIn('Projects — Term 1 — Finished exercises',
                      (target / MARKER).read_text(encoding='utf-8'))

    def test_wrong_account_stops_before_post(self):
        self.account = 'other@example.com'
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(0)

    def test_missing_remote_file_stops(self):
        self.files.pop()
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(0)

    def test_duplicate_remote_filename_stops(self):
        self.files.append({'name': '2.jpg', 'id': 'duplicate'})
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(0)

    def test_reordered_attachments_are_accepted(self):
        self.reorder = True
        self.assertTrue(self.run_flow())
        self.assertEqual(self.post_calls, 1)

    def test_observed_nested_post_and_duplicate_card_links(self):
        self.page.goto(self.pub.url)
        self.page.locator('#stream').evaluate(r'''(el, text) => {
          el.innerHTML = `<div data-stream-item-id="observed-post">
            <div data-stream-item-id="observed-post"><button>Menu</button></div>
            <div class="body pco8Kc"></div>
            <div data-stream-item-id="observed-post">
              <a href="https://drive.google.com/file/d/drive2/view" aria-label="Pielikums: 2.jpg"><img></a>
              <div data-attachment-id="card10">
                <a href="https://drive.google.com/file/d/drive10/view" aria-label="Pielikums: Attēls — 10.jpg"><img></a>
                <a href="https://drive.google.com/file/d/drive10/view" title="10.jpg">10.jpg</a>
              </div>
            </div></div>`;
          for (const line of text.split('\n')) {
            const span = document.createElement('span'); span.textContent = line;
            el.querySelector('.body').append(span, document.createElement('br'));
          }
        }''', self.pub.text)
        adapter = ClassroomPage(self.page, self.config)
        self.assertEqual(adapter.post_ids(), ['observed-post'])
        expected = [{'name': '2.jpg', 'id': 'drive2'}, {'name': '10.jpg', 'id': 'drive10'}]
        self.assertEqual(adapter.find_published(self.pub, expected, [])[0], 'observed-post')
        self.page.locator('[title="10.jpg"]').evaluate("el => el.href='https://drive.google.com/file/d/wrong/view'")
        with self.assertRaisesRegex(ValueError, 'card disagree'):
            adapter.find_published(self.pub, expected, [])

    def test_recover_existing_post_without_post_click(self):
        self.posts = [{'id': 'already-posted', 'text': self.pub.text, 'files': self.files}]
        expected = [{'name': item['name'], 'id': item['id']} for item in self.files]
        update_pending(self.folder, stage='posting', attachments=expected, baseline_post_ids=[])
        record = json.loads((self.folder / PENDING).read_text())
        verify_existing_page(self.page, self.folder, self.config, record)
        self.assertTrue((self.folder / MARKER).exists())
        self.assertEqual(self.post_calls, 0)
        self.assertEqual(self.picker_visits, 0)

    def test_recovery_missing_post_stays_uncertain_without_retry(self):
        update_pending(self.folder, stage='posting', attachments=self.files, baseline_post_ids=[])
        record = json.loads((self.folder / PENDING).read_text())
        with self.assertRaisesRegex(ValueError, 'Existing post could not be verified'):
            verify_existing_page(self.page, self.folder, self.config, record)
        self.assert_blocked(0)

    def test_metadata_in_picker_is_not_selected(self):
        self.files.extend([{'name': '.classroom-pending.json', 'id': 'pendingmetadata'},
                           {'name': '.classroom-draft.json', 'id': 'draftmetadata'}])
        self.assertTrue(self.run_flow())
        self.assertEqual([item['id'] for item in self.posts[0]['files']], ['drive2', 'drive10'])
        self.assertEqual(self.picker_visits, 1)

    def test_batch_selection_waits_for_each_async_update(self):
        self.delayed_selection = True
        self.assertTrue(self.run_flow())
        self.assertEqual([item['id'] for item in self.posts[0]['files']], ['drive2', 'drive10'])
        self.assertEqual(self.picker_visits, 1)

    def test_unrecognized_attachment_markup_reports_missing_links(self):
        self.config['ui'] = {'attachments': 'a.unrecognized-attachment'}
        with self.assertRaisesRegex(ValueError, 'No Drive attachment links were recognized'):
            self.run_flow()
        self.assert_blocked(0)

    def test_observed_composer_cover_card_and_open_links(self):
        self.page.goto(self.pub.url)
        self.page.locator('#composer').evaluate('''el => {
          el.hidden = false;
          el.querySelector('#attachments').innerHTML = `
            <div data-attachment-id="-123"><div>
              <a href="https://drive.google.com/open?id=drive2&amp;usp=classroom_web&amp;authuser=2"
                 title="2.jpg" aria-label="Pielikums: Attēls — 2.jpg"><div>2.jpg</div><div>Attēls</div></a>
              <span>Rādāmais attēls</span></div></div>
            <div data-attachment-id="-456"><div>
              <a href="https://drive.google.com/open?id=drive10&amp;usp=classroom_web&amp;authuser=2"
                 title="10.jpg" aria-label="Pielikums: Attēls — 10.jpg"><div>10.jpg</div><div>Attēls</div></a>
            </div></div>`;
        }''')
        adapter = ClassroomPage(self.page, self.config)
        self.assertEqual(adapter.attachments(adapter.composer(), self.pub.names),
                         [{'name': '2.jpg', 'id': 'drive2'}, {'name': '10.jpg', 'id': 'drive10'}])
        self.page.locator('[title="2.jpg"]').evaluate("el => el.remove()")
        with self.assertRaisesRegex(ValueError, 'Effective ui.attachments:'):
            adapter.attachments(adapter.composer(), self.pub.names)

    def test_existing_body_stops_duplicate(self):
        self.posts = [{'id': 'old-post', 'text': self.pub.text, 'files': self.files}]
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(0)

    def test_changed_local_file_stops_before_post(self):
        from unittest.mock import patch
        original = ClassroomPage.attach
        def changed(adapter, pub):
            result = original(adapter, pub)
            (pub.folder / pub.names[0]).write_bytes(b'changed')
            return result
        with patch.object(ClassroomPage, 'attach', changed), self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(0)

    def test_disappearing_post_after_reload_is_uncertain(self):
        self.persist = False
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(1)

    def test_wrong_persisted_drive_id_is_uncertain(self):
        self.reload_mutation = True
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assert_blocked(1)

    def test_network_failure_after_acceptance_does_not_retry(self):
        self.fail_click_response = True
        with self.assertRaises(ValueError):
            self.run_flow()
        self.assertEqual(len(self.posts), 1)
        self.assert_blocked(1)
