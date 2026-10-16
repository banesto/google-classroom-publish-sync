"""Local browser mechanics test; no Google services or account access."""
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from classroom_publisher.browser import normalized_text

with tempfile.TemporaryDirectory() as folder, sync_playwright() as p:
    context = p.chromium.launch_persistent_context(str(Path(folder) / 'profile'), channel='chrome', headless=True)
    try:
        page = context.new_page()
        page.set_content('''<div contenteditable="true" role="textbox"></div>
            <button onclick="window.clicks=(window.clicks||0)+1; document.querySelector('article').textContent=document.querySelector('[role=textbox]').innerText">Post</button>
            <article></article>''')
        text = 'Matemātika — 2026.10.15\n\nUzdevumi 35–40.'
        editor = page.locator('[contenteditable=true][role=textbox]:visible')
        editor.fill(text)
        assert normalized_text(editor.inner_text()) == normalized_text(text)
        page.get_by_role('button', name='Post', exact=True).click()
        assert normalized_text(page.locator('article').text_content()) == normalized_text(text)
        assert page.evaluate('window.clicks') == 1
        print('PASS: dedicated Chrome profile, multiline Unicode editor, single Post click.')
    finally:
        context.close()
