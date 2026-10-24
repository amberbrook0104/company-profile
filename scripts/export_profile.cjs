// Export with an existing Playwright install and local Chrome/Edge. No downloads.
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');

async function main() {
  const args = {};
  for (let i = 2; i < process.argv.length; i += 2) args[process.argv[i]] = process.argv[i + 1];
  if (!args['--html'] || !args['--png']) throw new Error('Usage: --html input.html --png output.png [--pdf output.pdf]');
  let chromium;
  try { ({chromium} = require('playwright')); }
  catch { try { ({chromium} = require('playwright-core')); }
    catch { throw new Error('Playwright unavailable. Set NODE_PATH to the existing package directory. No browser downloaded.'); } }
  const candidates = [args['--browser'],
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe'),
    process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Microsoft/Edge/Application/msedge.exe'),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe')];
  const executablePath = candidates.find(p => p && fs.existsSync(p));
  if (!executablePath) throw new Error('Local Chrome/Edge not found; specify --browser executable path.');
  const browser = await chromium.launch({headless: true, executablePath});
  try {
    const page = await browser.newPage({viewport: {width: 1660, height: 1160}, deviceScaleFactor: 1.5});
    await page.goto(pathToFileURL(path.resolve(args['--html'])).href);
    await page.evaluate(() => document.fonts.ready);
    const issues = await page.evaluate(() => {
      const root = document.querySelector('.sheet');
      if (!root) return ['Missing .sheet'];
      const outer = root.getBoundingClientRect();
      return [...document.querySelectorAll('[data-check],.metric,.hero,.sheet')].flatMap(el => {
        const r = el.getBoundingClientRect();
        const overflow = el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2;
        const outside = r.bottom > outer.bottom + 1 || r.right > outer.right + 1;
        return overflow || outside ? [el.className + ': content exceeds one-page layout'] : [];
      });
    });
    if (issues.length) throw new Error(issues.join('; '));
    fs.mkdirSync(path.dirname(path.resolve(args['--png'])), {recursive: true});
    await page.locator('.sheet').screenshot({path: path.resolve(args['--png'])});
    if (args['--pdf']) {
      await page.emulateMedia({media: 'print'});
      await page.pdf({path: path.resolve(args['--pdf']), width: '400mm', height: '275mm',
        margin: {top: 0, right: 0, bottom: 0, left: 0}, printBackground: true, preferCSSPageSize: true});
    }
    console.log(JSON.stringify({png: path.resolve(args['--png']), pdf: args['--pdf'] && path.resolve(args['--pdf']), overflow: false}));
  } finally { await browser.close(); }
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
