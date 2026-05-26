import csv
import os
import re
import sys
import time
import random  # 🔴 ランダム待機用

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 引数の受け取り
DEFAULT_PREFECTURE = "大阪府"
if len(sys.argv) > 1:
    TARGET_PREFECTURE = sys.argv[1]
else:
    TARGET_PREFECTURE = DEFAULT_PREFECTURE

safe_name = re.sub(r'[\\/:*?"<>|]', '_', TARGET_PREFECTURE)
OUTPUT_MOBILE = f"tsukulink_{safe_name}_携帯.csv"
OUTPUT_OTHER  = f"tsukulink_{safe_name}_固定その他.csv"

CSV_FIELDS = ["name", "hp_url", "address", "phone"]

def is_mobile_number(number):
    if not number: return False
    clean = re.sub(r'\D', '', str(number))
    if len(clean) == 11 and not clean.startswith('0800'):
        if clean.startswith(('070', '080', '090')):
            return True
    return False

def fetch_phone_logic(driver):
    try:
        page_text = driver.execute_script("return document.body.innerText;")
        page_text = page_text.translate(str.maketrans('０１２３４５６７８９－', '0123456789-'))
        pattern = r'0\d{1,4}[-( ]?\d{1,4}[-) ]?\d{3,4}'
        matches = re.findall(pattern, page_text)
        candidates = [re.sub(r'\D', '', m) for m in matches if len(re.sub(r'\D', '', m)) in [10, 11]]
        if not candidates: return None
        for c in candidates:
            if is_mobile_number(c): return c
        return candidates[0]
    except: return None

def deep_scan_external_site(driver, top_url):
    try:
        print(f"  ├─ 外部HP読込: {top_url}")
        driver.get(top_url)
        time.sleep(3)
        phone = fetch_phone_logic(driver)
        if phone: return phone

        print(f"  ├─ トップになし。深掘り探索中...", end="", flush=True)
        links = driver.find_elements(By.TAG_NAME, "a")
        target_url = None
        keywords = ["会社", "企業", "概要", "情報", "アクセス", "Company", "About", "Profile", "Access"]
        for link in links:
            try:
                href = link.get_attribute("href")
                text = link.text.strip()
                if href and any(k in (text + href) for k in keywords):
                    if not any(ex in href for ex in ["tsukulink.net", "zehitomo.com", "facebook", "instagram", "twitter", "line.me", "youtube", "tiktok"]):
                        target_url = href
                        break
            except: continue
        
        if target_url:
            print(f" [移動: {target_url}]")
            driver.get(target_url)
            time.sleep(3)
            return fetch_phone_logic(driver)
        
        print(" [なし]")
        return None
    except: return None

def write_to_csv(data, phone):
    target_file = OUTPUT_MOBILE if is_mobile_number(phone) else OUTPUT_OTHER
    file_exists = os.path.isfile(target_file)
    with open(target_file, 'a', newline='', encoding='utf_8_sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists: 
            writer.writeheader()
        writer.writerow(data)

def scrape_tsukulink():
    options = webdriver.ChromeOptions()
    
    # 🔴 【GitHub Actions/ボット対策】ヘッドレス環境で人間っぽく見せる設定
    options.add_argument('--headless')                 
    options.add_argument('--no-sandbox')               
    options.add_argument('--disable-dev-shm-usage')    
    options.add_argument('--window-size=1280,1000')    
    
    # 一般的なWindows ChromeのUser-Agentをセットしてヘッドレスを隠す
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.exclude_switches = ["enable-automation"]
    options.use_automation_extension = False

    driver = webdriver.Chrome(options=options)
    
    # 🔴 【ボット対策】JavaScriptの navigator.webdriver による自動判定を無効化
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    wait = WebDriverWait(driver, 15)
    total_extracted_count = 0

    try:
        driver.get("https://tsukulink.net/companies")
        print("==========================================")
        print(f" ツクリンク 抽出ボット（引数指定: {TARGET_PREFECTURE}）")
        print("==========================================")

        region_dropdown = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'c-form-select__input')][text()='地域を選択']"))
        )
        driver.execute_script("arguments[0].click();", region_dropdown)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "detail-search-job-type-modal__frame")))
        time.sleep(1)

        pref_xpath = f"//li[contains(@class, 'detail-search-job-type-modal__parent-group-item')][text()='{TARGET_PREFECTURE}']"
        try:
            pref_element = wait.until(EC.element_to_be_clickable((By.XPATH, pref_xpath)))
            driver.execute_script("arguments[0].click();", pref_element)
            time.sleep(1)
        except TimeoutException:
            print(f"【エラー】都道府県「{TARGET_PREFECTURE}」が見つかりませんでした。")
            return

        checkbox_label_xpath = f"//div[@class='detail-search-job-type-modal__child-title']//label[text()='{TARGET_PREFECTURE}']"
        try:
            checkbox_label = wait.until(EC.element_to_be_clickable((By.XPATH, checkbox_label_xpath)))
            driver.execute_script("arguments[0].click();", checkbox_label)
            time.sleep(1)
        except TimeoutException:
            print(f"【エラー】チェックボックスが見つかりませんでした。")
            return

        try:
            decision_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.detail-search-job-type-modal__decision-btn.btn-orange"))
            )
            driver.execute_script("arguments[0].click();", decision_button)
            time.sleep(1)
        except TimeoutException:
            print("【エラー】決定ボタンが見つかりませんでした。")
            return

        search_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.c-btn--mantis"))
        )
        driver.execute_script("arguments[0].click();", search_button)
        time.sleep(4)

        page_count = 1
        
        while True:
            print(f"\n>>> 第{page_count}ページ 処理開始...")
            try:
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "p-companies-list-item")))
            except TimeoutException:
                print("業者一覧の読み込みがタイムアウトしました。終了します。")
                break

            cards = driver.find_elements(By.CLASS_NAME, "p-companies-list-item")
            targets = []
            for card in cards:
                try:
                    name_element = card.find_element(By.CSS_SELECTOR, "a.p-companies-list-item__name")
                    comp_name = name_element.text.strip()
                    detail_btn = card.find_element(By.XPATH, ".//a[contains(@class, 'p-companies-list-item__btn') and text()='詳しく見る']")
                    detail_url = detail_btn.get_attribute("href")
                    if detail_url:
                        targets.append({"name": comp_name, "url": detail_url})
                except: continue

            if not targets:
                print(" -> 業者カードのURLが取得できませんでした。")
                break

            main_handle = driver.current_window_handle
            
            for index, target in enumerate(targets, start=1):
                print(f"[{page_count}P-{index}] {target['name']}")
                try:
                    driver.execute_script("window.open(arguments[0], '_blank');", target["url"])
                    driver.switch_to.window(driver.window_handles[-1])
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "p-companies-show__section")))
                    time.sleep(1.5)

                    comp_address = "記載なし"
                    try:
                        address_element = driver.find_element(By.CLASS_NAME, "p-companies-show-profile__info-address")
                        raw_address = " ".join(address_element.text.split())
                        comp_address = re.sub(r"〒?\s*\d{3}-\d{4}\s*", "", raw_address).strip()
                    except NoSuchElementException: pass

                    found_hp_url = None
                    try:
                        heading_elements = driver.find_elements(By.XPATH, "//h4[contains(text(), 'ウェブサイト')]")
                        for heading in heading_elements:
                            try:
                                link_el = heading.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'p-companies-show-detail__content')]/a")
                                url_candidate = link_el.get_attribute("href")
                                if url_candidate and url_candidate.startswith("http"):
                                    found_hp_url = url_candidate
                                    break
                            except NoSuchElementException: pass
                            
                            try:
                                div_el = heading.find_element(By.XPATH, "./following-sibling::div[contains(@class, 'p-companies-show-detail__content')]")
                                div_text = div_el.text.strip()
                                url_match = re.search(r'https?://[^\s]+', div_text)
                                if url_match:
                                    found_hp_url = url_match.group(0)
                                    break
                            except NoSuchElementException: pass
                    except Exception: pass

                    phone = None
                    if found_hp_url and "tsukulink.net" not in found_hp_url:
                        phone = deep_scan_external_site(driver, found_hp_url)
                        if phone: print(f"  └─ 外部HPで発見: {phone}")
                        else: print(f"  └─ 外部HPで発見: [なし]")
                    else: print(f"  └─ 外部HPリンクなし")

                    csv_data = {
                        "name": target["name"],
                        "hp_url": found_hp_url if (found_hp_url and "tsukulink.net" not in found_hp_url) else "記載なし",
                        "address": comp_address,
                        "phone": f"'{phone}" if phone else "記載なし"
                    }
                    write_to_csv(csv_data, phone)
                    total_extracted_count += 1
                    driver.close()
                    driver.switch_to.window(main_handle)
                except Exception as e:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(main_handle)
                    continue

                # 🔴 【ボット対策】毎回「2.5秒〜5.0秒」の間でランダムに待機時間を揺らし、人間が読んでいるように偽装
                time.sleep(random.uniform(2.5, 5.0))

            print(f"\n--- 第{page_count}ページの20件が完了。次ページへ移動します ---")
            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "a.c-pagination__link--next")
                old_next_button = next_button
                driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", next_button)
                wait.until(EC.staleness_of(old_next_button))
                time.sleep(3) 
                page_count += 1
            except (NoSuchElementException, TimeoutException):
                print("\n「次へ」ボタンが見つからないか、最終ページに到達しました。")
                break
    finally:
        driver.quit()
        print("\n==========================================")
        print(" 処理が正常に終了しました！")
        print(f" 対象地域: {TARGET_PREFECTURE}")
        print(f" 抽出件数: 【 {total_extracted_count} 件 】完了しました。")
        print("==========================================")

if __name__ == "__main__":
    scrape_tsukulink()
