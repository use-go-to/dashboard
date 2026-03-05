#!/usr/bin/env python3
"""
Script standalone lancé en subprocess pour scraper Pronote.
Contourne le conflit Playwright Sync API / asyncio loop de gevent.
"""
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

            # ETAPE 1 - Toutatice
            print('📍 Etape 1: Toutatice...', flush=True)
            page.goto('https://www.toutatice.fr/', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            page.wait_for_selector('a.btn-login', timeout=10000)
            page.click('a.btn-login')
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(3000)
            print(f'   URL: {page.url}', flush=True)

            # ETAPE 2 - EduConnect
            print('📍 Etape 2: EduConnect...', flush=True)
            page.wait_for_selector('button.card-button', timeout=10000)
            page.click('button.card-button')
            page.wait_for_timeout(4000)
            print(f'   URL: {page.url}', flush=True)

            # ETAPE 3 - Identifiants (formulaire en 2 passes)
            print('📍 Etape 3: Identifiants...', flush=True)

            # Dump tous les inputs visibles
            all_inputs = page.eval_on_selector_all(
                'input:not([type="hidden"])',
                'els => els.map(e => ({id:e.id, name:e.name, type:e.type}))'
            )
            print(f'   Inputs visibles: {all_inputs}', flush=True)

            # Remplir username
            username_filled = False
            for sel in ['#username', 'input[name="username"]', 'input[type="text"]:visible',
                        'input[autocomplete="username"]']:
                try:
                    el = page.locator(sel).first
                    el.wait_for(state='visible', timeout=3000)
                    el.triple_click()
                    el.fill(PRONOTE_USER)
                    username_filled = True
                    print(f'   ✅ Username ({sel}): {PRONOTE_USER}', flush=True)
                    break
                except:
                    pass

            if not username_filled:
                print('   ❌ Username non trouvé!', flush=True)

            # Cliquer Suivant si password pas encore visible
            pwd_visible = False
            try:
                page.locator('input[type="password"]').first.wait_for(state='visible', timeout=2000)
                pwd_visible = True
            except:
                pass

            if not pwd_visible:
                print('   ⏩ Clic Suivant...', flush=True)
                for sel in ['#bouton_valider', 'button[type="submit"]', 'input[type="submit"]']:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=1000):
                            el.click()
                            break
                    except:
                        pass
                page.wait_for_timeout(3000)

            # Remplir password
            try:
                pwd = page.locator('input[type="password"]').first
                pwd.wait_for(state='visible', timeout=8000)
                pwd.fill(PRONOTE_PASS)
                print('   ✅ Password saisi', flush=True)
            except Exception as e:
                print(f'   ❌ Password: {e}', flush=True)

            # Soumettre
            for sel in ['#bouton_valider', 'button[type="submit"]', 'input[type="submit"]']:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=1000):
                        el.click()
                        print(f'   ✅ Submit: {sel}', flush=True)
                        break
                except:
                    pass

            page.wait_for_timeout(8000)
            print(f'   URL après login: {page.url}', flush=True)
            print(f'   Titre: {page.title()}', flush=True)

            # Vérifier si on est bien connecté (pas encore sur EduConnect)
            if 'educonnect' in page.url.lower():
                # Dump HTML pour debug
                html = page.inner_html('body')
                print(f'   ⚠️ Encore sur EduConnect! HTML snippet: {html[:400]}', flush=True)
                browser.close()
                return {'notes_recentes': [], 'average': '0',
                        'error': f'Login EduConnect échoué. URL={page.url}'}

            # ETAPE 4 - Tuile Pronote
            print('📍 Etape 4: Tuile Pronote...', flush=True)
            page.wait_for_timeout(3000)

            pronote_link = None
            for sel in ['[data-dnma-outil="PRONOTE"]', 'a[href*="pronote"]',
                        'a[title*="Pronote"]', 'a[title*="PRONOTE"]',
                        'a:has-text("Pronote")', 'a:has-text("PRONOTE")',
                        '[class*="pronote"]']:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=3000):
                        pronote_link = el
                        print(f'   ✅ Pronote: {sel}', flush=True)
                        break
                except:
                    pass

            if not pronote_link:
                links = page.eval_on_selector_all('a', 'els => els.map(e => e.textContent.trim()).filter(t=>t.length>0 && t.length<30)')
                print(f'   ❌ Pronote introuvable. Textes liens: {links[:15]}', flush=True)
                browser.close()
                return {'notes_recentes': [], 'average': '0',
                        'error': f'Tuile Pronote introuvable. URL={page.url}'}

            # Cliquer Pronote
            try:
                with ctx.expect_page(timeout=8000) as new_page_info:
                    pronote_link.click()
                pronote_page = new_page_info.value
                print('   ✅ Nouvel onglet Pronote', flush=True)
            except:
                pronote_link.click()
                page.wait_for_timeout(3000)
                pronote_page = page
                print('   ⚠️ Même onglet', flush=True)

            # ETAPE 5 - Interface Pronote
            print('📍 Etape 5: Interface Pronote...', flush=True)
            try:
                pronote_page.wait_for_selector(
                    '.label-menu_niveau0, ul.liste-cours, #GInterface',
                    timeout=30000
                )
                print('   ✅ Interface chargée', flush=True)
            except:
                pronote_page.wait_for_timeout(8000)

            # ETAPE 6 - Notes
            print('📍 Etape 6: Notes...', flush=True)
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
                    note_float = float(note_val)
                    note_sur_int = int(note_sur)
                    note_20 = round(note_float * 20 / note_sur_int, 2) if note_sur_int else note_float
                    notes_raw.append({
                        'date_display': date_display,
                        'matiere': matiere_nom + (' > ' + sous_type if sous_type else ''),
                        'note_brute': note_display or f'{note_val}/{note_sur}',
                        'note_sur_20': note_20,
                        'coefficient': 1,
                    })

            avg = round(sum(n['note_sur_20'] for n in notes_raw) / len(notes_raw), 2) if notes_raw else 0
            print(f'   ✅ {len(notes_raw)} notes, moyenne={avg}', flush=True)
            browser.close()
            return {'notes_recentes': notes_raw, 'average': str(avg)}

    except Exception as e:
        print(f'❌ Erreur: {e}', flush=True)
        return {'notes_recentes': [], 'average': '0', 'error': str(e)}

if __name__ == '__main__':
    result = scrape()
    print(json.dumps(result, ensure_ascii=False))
