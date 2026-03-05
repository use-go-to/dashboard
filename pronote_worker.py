#!/usr/bin/env python3
"""Script standalone Pronote scraper - sélecteurs exacts depuis HTML réel"""
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

            # ── ETAPE 1 : Toutatice ──────────────────────────────────────────
            print('STEP1: Toutatice', flush=True)
            page.goto('https://www.toutatice.fr/', wait_until='domcontentloaded', timeout=30000)
            page.wait_for_timeout(2000)
            # <a href="https://ent.toutatice.fr/portail/auth/" class="btn btn-login ...">
            page.wait_for_selector('a.btn-login', timeout=10000)
            page.click('a.btn-login')
            page.wait_for_load_state('domcontentloaded')
            page.wait_for_timeout(3000)
            print(f'STEP1_URL: {page.url}', flush=True)

            # ── ETAPE 2 : Bouton EduConnect ──────────────────────────────────
            print('STEP2: EduConnect', flush=True)
            # <button type="submit" class="card-body card-button">
            page.wait_for_selector('button.card-button', timeout=10000)
            page.click('button.card-button')
            page.wait_for_timeout(5000)
            print(f'STEP2_URL: {page.url}', flush=True)

            # ── ETAPE 3 : Login EduConnect ───────────────────────────────────
            # <input class="fr-input" type="text" id="username" name="j_username" ...>
            # <input class="fr-input" type="password" id="password" name="j_password" ...>
            # <button id="bouton_valider" ...>
            print('STEP3: Login', flush=True)
            page.wait_for_selector('#username', timeout=15000)
            page.wait_for_timeout(2000)
            print(f'PAGE_URL_BEFORE_LOGIN: {page.url}', flush=True)

            # Vider et remplir username via triple_click + type (simule clavier réel)
            page.click('#username', click_count=3)
            page.wait_for_timeout(300)
            page.keyboard.type(PRONOTE_USER, delay=80)
            val_u = page.input_value('#username')
            print(f'USERNAME_VALUE: "{val_u}"', flush=True)

            # Tab pour passer au champ password
            page.keyboard.press('Tab')
            page.wait_for_timeout(500)

            # Vider et remplir password
            page.click('#password', click_count=3)
            page.wait_for_timeout(300)
            page.keyboard.type(PRONOTE_PASS, delay=80)
            val_p = page.input_value('#password')
            print(f'PASSWORD_LEN: {len(val_p)}', flush=True)

            # Cliquer bouton valider
            page.wait_for_timeout(500)
            page.click('#bouton_valider')
            page.wait_for_timeout(8000)
            print(f'STEP3_URL: {page.url}', flush=True)
            print(f'STEP3_TITLE: {page.title()}', flush=True)

            if 'educonnect' in page.url.lower():
                print(f'LOGIN_FAILED: encore sur EduConnect', flush=True)
                browser.close()
                return {'notes_recentes': [], 'average': '0', 'emploi_du_temps': [],
                        'cantine': [], 'error': f'Login EduConnect échoué. URL={page.url}'}

            # ── ETAPE 4 : Tuile Pronote ──────────────────────────────────────
            # <a data-dnma-outil="PRONOTE" ...>
            print('STEP4: Tuile Pronote', flush=True)
            page.wait_for_timeout(3000)
            page.wait_for_selector('[data-dnma-outil="PRONOTE"]', timeout=20000)
            pronote_link = page.locator('[data-dnma-outil="PRONOTE"]').first
            print('PRONOTE_FOUND', flush=True)

            try:
                with ctx.expect_page(timeout=10000) as new_page_info:
                    pronote_link.click()
                pronote_page = new_page_info.value
                pronote_page.wait_for_load_state('domcontentloaded')
                print('PRONOTE_NEW_TAB: OK', flush=True)
            except Exception as e:
                print(f'PRONOTE_SAME_TAB: {e}', flush=True)
                pronote_link.click()
                page.wait_for_timeout(5000)
                pronote_page = page

            # ── ETAPE 5 : Attendre interface Pronote ─────────────────────────
            print('STEP5: Interface Pronote', flush=True)
            try:
                pronote_page.wait_for_selector(
                    '.label-menu_niveau0, ul.liste-cours, #GInterface',
                    timeout=30000
                )
                print('PRONOTE_LOADED', flush=True)
            except Exception as e:
                print(f'PRONOTE_LOAD_TIMEOUT: {e}', flush=True)
                pronote_page.wait_for_timeout(8000)

            # ── ETAPE 6 : Emploi du temps (page accueil) ─────────────────────
            # <ul class="liste-cours m-top-l">
            print('STEP6: Emploi du temps', flush=True)
            emploi_du_temps = []
            try:
                pronote_page.wait_for_selector('ul.liste-cours', timeout=8000)
                cours_html = pronote_page.inner_html('ul.liste-cours')
                soup_edt = BeautifulSoup(cours_html, 'html.parser')
                for li in soup_edt.select('li.flex-contain'):
                    sr = li.select_one('span.sr-only')
                    heures = li.select('.container-heures div')
                    matiere_el = li.select_one('li.libelle-cours')
                    prof_els = li.select('ul.container-cours li')
                    salle = prof_els[-1].get_text(strip=True) if len(prof_els) > 2 else ''
                    prof = prof_els[1].get_text(strip=True) if len(prof_els) > 1 else ''
                    en_cours = 'en-cours' in li.get('class', [])
                    emploi_du_temps.append({
                        'label': sr.get_text(strip=True) if sr else '',
                        'heure_debut': heures[0].get_text(strip=True) if heures else '',
                        'heure_fin': heures[1].get_text(strip=True) if len(heures) > 1 else '',
                        'matiere': matiere_el.get_text(strip=True) if matiere_el else '',
                        'prof': prof,
                        'salle': salle,
                        'en_cours': en_cours,
                    })
                print(f'EDT: {len(emploi_du_temps)} cours', flush=True)
            except Exception as e:
                print(f'EDT_ERROR: {e}', flush=True)

            # ── ETAPE 7 : Notes ───────────────────────────────────────────────
            print('STEP7: Notes', flush=True)
            notes_raw = []
            try:
                # Cliquer menu Notes
                notes_menu = pronote_page.locator('.label-menu_niveau0', has_text='Notes')
                notes_menu.wait_for(timeout=10000)
                notes_menu.click()
                pronote_page.wait_for_timeout(800)

                # Cliquer "Mes notes" (data-genre="198")
                mes_notes = pronote_page.locator('[data-genre="198"]')
                mes_notes.wait_for(timeout=5000)
                mes_notes.click()
                pronote_page.wait_for_timeout(2000)

                # Sélectionner Trimestre 2
                combobox = pronote_page.locator('[role="combobox"][aria-label="Sélectionnez une période"]')
                combobox.wait_for(timeout=10000)
                current = combobox.text_content() or ''
                print(f'PERIODE_ACTUELLE: {current}', flush=True)

                if 'Trimestre 2' not in current:
                    combobox.click()
                    pronote_page.wait_for_timeout(500)
                    t2 = pronote_page.locator('[role="option"]:has-text("Trimestre 2")')
                    t2.first.wait_for(timeout=5000)
                    t2.first.click()
                    pronote_page.wait_for_timeout(2000)

                pronote_page.wait_for_selector('[role="tree"]', timeout=10000)
                html = pronote_page.inner_html('[role="tree"]')
                soup = BeautifulSoup(html, 'html.parser')

                for item in soup.select('[role="treeitem"]'):
                    date_el = item.select_one('time')
                    date_display = date_el.get_text(strip=True) if date_el else ''
                    titres = item.select('div.titre-principal div.ie-ellipsis')
                    matiere_full = titres[0].get_text(strip=True) if titres else ''
                    intitule = titres[1].get_text(strip=True) if len(titres) > 1 else ''
                    matiere_parts = matiere_full.split('>')
                    matiere_nom = matiere_parts[0].strip()
                    sous_type = matiere_parts[1].strip() if len(matiere_parts) > 1 else ''
                    # Moyenne classe
                    moy_el = item.select_one('.ie-sous-titre')
                    moy_classe = moy_el.get_text(strip=True) if moy_el else ''
                    # Note élève via aria-label
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
                            'intitule': intitule,
                            'note_brute': note_display or f'{note_val}/{note_sur}',
                            'note_sur_20': n20,
                            'moy_classe': moy_classe,
                            'coefficient': 1,
                        })

                print(f'NOTES: {len(notes_raw)} notes', flush=True)
            except Exception as e:
                print(f'NOTES_ERROR: {e}', flush=True)

            # ── ETAPE 8 : Menu cantine ────────────────────────────────────────
            print('STEP8: Cantine', flush=True)
            cantine = []
            try:
                # Menu Communication > Menu
                comm_menu = pronote_page.locator('.label-menu_niveau0', has_text='Communication')
                comm_menu.wait_for(timeout=10000)
                comm_menu.click()
                pronote_page.wait_for_timeout(800)

                # data-genre="10" = Menu cantine
                menu_item = pronote_page.locator('[data-genre="10"]')
                menu_item.wait_for(timeout=5000)
                menu_item.click()
                pronote_page.wait_for_timeout(2000)

                pronote_page.wait_for_selector('div.menu-cantine', timeout=10000)
                cantine_html = pronote_page.inner_html('div.menu-cantine')
                soup_c = BeautifulSoup(cantine_html, 'html.parser')

                for day_div in soup_c.select('[role="group"]'):
                    day_label = day_div.get('aria-label', '')
                    date_h2 = day_div.select_one('h2')
                    date_str = date_h2.get_text(strip=True) if date_h2 else day_label
                    plats = []
                    for aliment in day_div.select('div.aliment'):
                        texte = aliment.get_text(strip=True)
                        bio = bool(aliment.select_one('[aria-label*="Biologique"]'))
                        plats.append({'plat': texte, 'bio': bio})
                    cantine.append({'jour': date_str, 'plats': plats})

                print(f'CANTINE: {len(cantine)} jours', flush=True)
            except Exception as e:
                print(f'CANTINE_ERROR: {e}', flush=True)

            browser.close()

            avg = round(sum(n['note_sur_20'] for n in notes_raw) / len(notes_raw), 2) if notes_raw else 0
            print(f'DONE: {len(notes_raw)} notes moyenne={avg}', flush=True)

            return {
                'notes_recentes': notes_raw,
                'average': str(avg),
                'emploi_du_temps': emploi_du_temps,
                'cantine': cantine,
            }

    except Exception as e:
        print(f'FATAL: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return {'notes_recentes': [], 'average': '0', 'emploi_du_temps': [],
                'cantine': [], 'error': str(e)}

if __name__ == '__main__':
    result = scrape()
    print(json.dumps(result, ensure_ascii=False))
