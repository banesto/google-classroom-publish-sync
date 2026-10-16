# Verification record

## Current implementation — 2026-10-16

- Version: 0.2.0; Python with Playwright 1.60.0.
- Host tested: macOS, Python 3.9.6, installed Google Chrome.
- 23 automated tests passed: 12 core/safety tests and 11 browser integration tests.
- Browser tests used a fresh temporary Chrome profile and intercepted every request. No real Google services were contacted.
- Full fixture flow passed: two naturally sorted Drive files → draft review → exactly one Post request → persisted-post reload → success marker with filenames, Drive IDs, text and URL.
- Negative cases passed: wrong account, missing/duplicate remote files, reordered attachments, edited local files, an existing matching post, cancelled review, missing persisted post, wrong persisted Drive ID, and a connection failure after acceptance. None caused an automatic retry.
- Version 0.2.0 wheel build passed. CLI help checked. Windows command quoting and local single-instance locking covered by tests.
- Windows PowerShell installer, registry integration on Windows, and Tk dialogs on Windows: NOT EXECUTED on a Windows 11 host.
- Google login and the real Classroom/Drive UI: NOT VERIFIED. Default UI selectors are provisional and require live calibration.
- No real Classroom post has been created by this development run.

## Required first live test

Status: NOT RUN — awaiting a child account, configured folder and class URL.

- OS / Chrome / Python / Playwright versions:
- Date and tester:
- Dedicated child profile and correct active email verified:
- Login persists after closing and reopening the profile:
- Teacher allows student Stream posts:
- Local class root maps to the correct online My Drive path:
- Two original synced Drive files visible in picker:
- Actual composer/editor/Drive picker selectors:
- Breadcrumb names and file-ID attribute verified:
- No Upload or Copy used:
- Draft names/count/Drive IDs/order match:
- Exactly one Post click:
- New stable Stream item and full text persist after reload:
- Published attachment IDs/names/order match:
- Post link, if retrievable:
- Success marker verified:
- Attempting the same folder again is blocked:
- Windows 11 installer and Explorer menu tested:
- Failures / limitations / required changes:

Do not commit passwords, cookies, live screenshots or browser-profile data. Keep student-specific configuration local.
