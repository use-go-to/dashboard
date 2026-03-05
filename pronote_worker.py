#!/usr/bin/env python3
"""Script standalone pour scraper Pronote via subprocess (évite conflit asyncio/gevent)"""
import sys, json, os, re
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

PRONOTE_USER = os.environ.get('PRONOTE_USER', 'd.lecointre10')
PRONOTE_PASS = os.environ.get('PRONOTE_PASS', 'David@35160')

def scrape():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox','--disable-setuid-sandbox',
                      '--disable-dev-shm-usage','--disable-gpu']
            )
            ctx = browser.new_context(
                viewport={'width':1280,'height':900},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                locale='fr-FR',
            )
            ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
            page = ctx.new_page()

            # ETAPE 1
            print('STEP1: Toutatice', flush=True)
            page.goto('https://www.toutatice.fr/', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            page.wait_for_selector('a.btn-login', timeout=10000)
            page.click('a.btn-login')
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(3000)
            print(f'STEP1_URL: {page.url}', flush=True)

            # ETAPE 2
            print('STEP2: EduConnect button', flush=True)
            page.wait_for_selector('button.card-button', timeout=10000)
            page.click('button.card-button')
            page.wait_for_timeout(5000)
            print(f'STEP2_URL: {page.url}', flush=True)

            # ETAPE 3 - Attendre rendu JS complet
            print('STEP3: Login form', flush=True)
            try:
                page.wait_for_load_state('networkidle', timeout=8000)
            except:
                pass
            page.wait_for_timeout(3000)

            # Dump complet des inputs
            all_inputs = page.evaluate('''() => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id, name: i.name, type: i.type, 
                    visible: i.offsetParent !== null,
                    placeholder: i.placeholder,
                    value: i.value
                }));
            }''')
            print(f'INPUTS: {json.dumps(all_inputs)}', flush=True)

            # Remplir username via JS direct (contourne les frameworks React/Vue)
            filled = page.evaluate(f'''() => {{
                const candidates = [
                    document.getElementById('username'),
                    document.querySelector('input[name="username"]'),
                    document.querySelector('input[type="text"]'),
                    document.querySelector('input[autocomplete="username"]'),
                    document.querySelector('input:not([type="hidden"]):not([type="password"])'),
                ];
                for (const inp of candidates) {{
                    if (inp) {{
                        inp.focus();
                        inp.value = "{PRONOTE_USER}";
                        inp.dispatchEvent(new Event('input', {{bubbles:true}}));
                        inp.dispatchEvent(new Event('change', {{bubbles:true}}));
                        inp.dispatchEvent(new KeyboardEvent('keyup', {{bubbles:true}}));
                        return inp.id + '|' + inp.name + '|' + inp.value;
                    }}
                }}
                return "not_found";
            }}''')
            print(f'USERNAME_FILL: {filled}', flush=True)

            page.wait_for_timeout(500)
            page.keyboard.press('Tab')
            page.wait_for_timeout(300)

            # Submit étape 1
            for sel in ['#bouton_valider', 'button[type="submit"]', 'input[type="submit"]']:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f'SUBMIT1: {sel}', flush=True)
                        break
                except:
                    pass

            page.wait_for_timeout(4000)
            print(f'STEP3_URL: {page.url}', flush=True)

            # Page password
            try:
                pwd = page.locator('input[type="password"]').first
                pwd.wait_for(state='visible', timeout=8000)
                pwd.fill(PRONOTE_PASS)
                print('PASSWORD: OK', flush=True)
            except Exception as e:
                print(f'PASSWORD_ERR: {e}', flush=True)

            for sel in ['#bouton_valider', 'button[type="submit"]', 'input[type="submit"]']:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f'SUBMIT2: {sel}', flush=True)
                        break
                except:
                    pass

            page.wait_for_timeout(8000)
            print(f'AFTER_LOGIN_URL: {page.url}', flush=True)
            print(f'AFTER_LOGIN_TITLE: {page.title()}', flush=True)

            if 'educonnect' in page.url.lower():
                html = page.inner_html('body')[:1000]
                print(f'STILL_EDUCONNECT: {html}', flush=True)
                browser.close()
                return {'notes_recentes': [], 'average': '0',
                        'error': f'Login EduConnect échoué URL={page.url}'}

            # ETAPE 4 - Tuile Pronote
            print('STEP4: Pronote tile', flush=True)
            page.wait_for_timeout(3000)

            pronote_link = None
            for sel in ['[data-dnma-outil="PRONOTE"]', 'a[href*="pronote"]',
                        'a[title*="Pronote"]', 'a:has-text("Pronote")',
                        'a:has-text("PRONOTE")', '[class*="pronote"]']:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        pronote_link = el
                        print(f'PRONOTE_FOUND: {sel}', flush=True)
                        break
                except:
                    pass

            if not pronote_link:
                texts = page.evaluate('() => Array.from(document.querySelectorAll("a")).map(a=>a.textContent.trim()).filter(t=>t.length>0&&t.length<40)')
                print(f'PRONOTE_NOT_FOUND links: {texts[:20]}', flush=True)
                browser.close()
                return {'notes_recentes': [], 'average': '0',
                        'error': f'Tuile Pronote introuvable. URL={page.url}'}

            try:
                with ctx.expect_page(timeout=8000) as new_page_info:
                    pronote_link.click()
                pronote_page = new_page_info.value
                print('PRONOTE_NEW_TAB: OK', flush=True)
            except:
                pronote_link.click()
                page.wait_for_timeout(3000)
                pronote_page = page

            # ETAPE 5 - Interface Pronote
            print('STEP5: Pronote interface', flush=True)
            try:
                pronote_page.wait_for_selector(
                    '.label-menu_niveau0, ul.liste-cours, #GInterface',
                    timeout=30000
                )
                print('PRONOTE_LOADED: OK', flush=True)
            except:
                pronote_page.wait_for_timeout(8000)

            # ETAPE 6 - Notes
            print('STEP6: Notes', flush=True)
            notes_menu = pronote_page.locator('.label-menu_niveau0', has_text='Notes')
            notes_menu.wait_for(timeout=10000)
            notes_menu.click()
            pronote_page.wait_for_timeout(800)

            mes_notes = pronote_page.locator('[data-genre="198"]')
            mes_notes.wait_for(timeout=5000)
            mes_notes.click()
            pronote_page.wait_for_timeout(2000)

            selector = pronote_page.locator('[role="combobox"][aria-label="Sélectionnez une période"]')
            selector.wait_for(timeout=10000)
            current = selector.text_content()
            if 'Trimestre 2' not in (current or ''):
                selector.click()
                pronote_page.wait_for_timeout(500)
                opt = pronote_page.locator('[role="option"]:has-text("Trimestre 2")')
                opt.first.wait_for(timeout=5000)
                opt.first.click()
                pronote_page.wait_for_timeout(2000)

            pronote_page.wait_for_selector('[role="tree"]', timeout=10000)
            html = pronote_page.inner_html('[role="tree"]')
            soup = BeautifulSoup(html, 'html.parser')

            notes_raw = []
            for item in soup.select('[role="treeitem"]'):
                date_el = item.select_one('time')
                date_display = date_el.get_text(strip=True) if date_el else ''
                titres = item.select('div.titre-principal div.ie-ellipsis')
                matiere_full = titres[0].get_text(strip=True) if titres else ''
                matiere_parts = matiere_full.split('>')
                matiere_nom = matiere_parts[0].strip()
                sous_type = matiere_parts[1].strip() if len(matiere_parts) > 1 else ''
                note_zone = item.select_one('[aria-label*="Note élève"]')
                note_aria = note_zone.get('aria-label', '') if note_zone else ''
                note_match = re.search(r'Note élève\s*:\s*([\d,\.]+)(?:/([\d]+))?', note_aria)
                note_val = note_match.group(1).replace(',', '.') if note_match else ''
                note_sur = note_match.group(2) if (note_match and note_match.group(2)) else '20'
                note_el = item.select_one('span.note-devoir')
                note_display = note_el.get_text(strip=True) if note_el else ''
                if note_val:
                    nf = float(note_val)
                    ns = int(note_sur)
                    n20 = round(nf * 20 / ns, 2) if ns else nf
                    notes_raw.append({
                        'date_display': date_display,
                        'matiere': matiere_nom + (' > ' + sous_type if sous_type else ''),
                        'note_brute': note_display or f'{note_val}/{note_sur}',
                        'note_sur_20': n20, 'coefficient': 1,
                    })

            avg = round(sum(n['note_sur_20'] for n in notes_raw) / len(notes_raw), 2) if notes_raw else 0
            print(f'NOTES_OK: {len(notes_raw)} notes moyenne={avg}', flush=True)
            browser.close()
            return {'notes_recentes': notes_raw, 'average': str(avg)}

    except Exception as e:
        print(f'FATAL_ERROR: {e}', flush=True)
        return {'notes_recentes': [], 'average': '0', 'error': str(e)}

if __name__ == '__main__':
    result = scrape()
    print(json.dumps(result, ensure_ascii=False))
