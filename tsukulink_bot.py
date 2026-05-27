import csv
import os
import re
import sys
import time
import random
import requests  # Slackへのファイル送信に使用

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# ========================================================
# 【設定項目】コマンドライン引数から条件を受け取る
# ========================================================
TARGET_PREFECTURE = sys.argv[1] if len(sys.argv) > 1 else "大阪府"
START_PAGE = int(sys.argv[2]) if len(sys.argv) > 2 else 1
END_PAGE = int(sys.argv[3]) if len(sys.argv) > 3 else 5

# 文字化け対策のため、成果物のファイル名はローマ字（keitai / kotei）に固定
safe_name = re.sub(r'[\\/:*?"<>|]', '_', TARGET_PREFECTURE)
OUTPUT_MOBILE = f"tsukulink_{safe_name}_page{START_PAGE}_{END_PAGE}_keitai.csv"
OUTPUT_OTHER  = f"tsukulink_{safe_name}_page{START_PAGE}_{END_PAGE}_kotei.csv"

CSV_FIELDS = ["name", "hp_url", "address", "phone"]


def upload_to_slack(file_path, comment):
    """🟢 処理の最後に、完成したCSVファイルをSlackへ直接アップロードする関数"""
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    channel_id = os.environ.get("SLACK_CHANNEL_ID")
    
    if not bot_token or not channel_id:
        print(f"  [Slack] 設定が足りないため、{file_path} のアップロードをスキップします。")
        return

    if not os.path.exists(file_path):
        print(f"  [Slack] 送信対象のファイルが存在しません: {file_path}")
        return

    print(f"  🚀 Slackへファイルをアップロード中: {file_path} ...")
    
    # SlackのファイルアップロードAPI (v2)
    url = "https://slack.com/api/files.upload"
    headers = {"Authorization": f"Bearer {bot_token}"}
    
    # 送信するデータとファイルの準備
    payload = {
        "channels": channel_id,
        "initial_comment": comment
    }
    
    with open(file_path, "rb") as f:
        files = {"file": f}
        try:
            response = requests.post(url, headers=headers, data=payload, files=files, timeout=30)
            result = response.json()
            if result.get("ok"):
                print(f"  └─ Slackへのファイルアップロードに成功しました！ ({file_path})")
            else:
                print(f"  └─ Slackアップロードエラー: {result.get('error')}")
        except Exception as e:
            print(f"  └─ Slack送信中に例外が発生しました: {e}")


def is_mobile_number(number):
    """【zehitomo完全移植】携帯電話番号か判定"""
    if not number: return False
    clean = re.sub(r'\D', '', str(number))
    if len(clean) == 11 and not clean.startswith('0800'):
        if clean.startswith(('070', '080', '090')):
            return True
    return False


def fetch_phone_logic(driver):
    """【zehitomo完全移植】ページ内のテキストから電話番号パターンを抽出"""
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
    """【zehitomo完全移植】外部HPのトップおよび下層を深掘りして電話番号を探索"""
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
    """【zehitomo完全移植】携帯と固定その他に自動分割してCSVへ書き出し"""
    target_file = OUTPUT_MOBILE if is_mobile_number(phone) else OUTPUT_OTHER
    file_exists = os.path.isfile(target_file)
    with open(target_file, 'a', newline='', encoding='utf_8_sig') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists: 
            writer.writeheader()
        writer.writerow(data)


def scrape_tsukulink():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')                 
    options.add_argument('--no-sandbox')               
    options.add_argument('--disable-dev-shm-usage')    
    options.add_argument('--window-size=1280,1000')    
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.exclude_switches = ["enable-automation"]
    options.use_automation_extension = False

    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    wait = WebDriverWait(driver, 15)
    total_extracted_count = 0

    try:
        driver.get("https://tsukulink.net/companies")
        print("==========================================")
        print(f" ツクリンク 分割並列ボット (Slackファイル送信版)")
        print(f" 対象地域: {TARGET_PREFECTURE}")
        print(f" 担当範囲: {START_PAGE} ページ ～ {END_PAGE} ページ")
        print("==========================================")

        # 1. 地域選択モーダルを開く
        region_dropdown = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'c-form-select__input')][text()='地域を選択']"))
        )
        driver.execute_script("arguments[0].click();", region_dropdown)
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "detail-search-job-type-modal__frame")))
        time.sleep(1)

        # 2. 都道府県を選択
        pref_xpath = f"//li[contains(@class, 'detail-search-job-type-modal__parent-group-item')][text()='{TARGET_PREFECTURE}']"
        try:
            pref_element = wait.until(EC.element_to_be_clickable((By.XPATH, pref_xpath)))
            driver.execute_script("arguments[0].click();", pref_element)
            time.sleep(1)
        except TimeoutException:
            print(f"【エラー】都道府県「{TARGET_PREFECTURE}」が見つかりませんでした。")
            return

        # 3. 一括チェックボックスをクリック
        checkbox_label_xpath = f"//div[@class='detail-search-job-type-modal__child-title']//label[text()='{TARGET_PREFECTURE}']"
        try:
            checkbox_label = wait.until(EC.element_to_be_clickable((By.XPATH, checkbox_label_xpath)))
            driver.execute_script("arguments[0].click();", checkbox_label)
            time.sleep(1)
        except TimeoutException:
            print(f"【エラー】チェックボックスが見つかりませんでした。")
            return

        # 4. 「決定」ボタンをクリックして確定
        try:
            decision_button = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.detail-search-job-type-modal__decision-btn.btn-orange"))
            )
            driver.execute_script("arguments[0].click();", decision_button)
            time.sleep(1)
        except TimeoutException:
            print("【エラー】決定ボタンが見つかりませんでした。")
            return

        # 5. 検索を実行して一覧を出す
        search_button = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.c-btn--mantis"))
        )
        driver.execute_script("arguments[0].click();", search_button)
        time.sleep(4)

        # 指定ページへワープ
        if START_PAGE > 1:
            print(f"\n🚀 ツクリンクの内部処理を偽装し、{START_PAGE} ページ目へワープします...")
            try:
                target_link = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[data-page]")))
                driver.execute_script(f"""
                    arguments[0].setAttribute('data-page', '{START_PAGE}');
                    arguments[0].setAttribute('href', '/companies?page={START_PAGE}');
                """, target_link)
                driver.execute_script("arguments[0].click();", target_link)
                time.sleep(5)
                print(f" -> {START_PAGE} ページ目へのワープに成功しました。")
            except Exception as e:
                print(f"【警告】ワープ処理に失敗しました。1ページ目から開始します。 エラー: {e}")
                pass

        page_count = START_PAGE
        
        while True:
            print(f"\n>>> 第{page_count}ページ 処理開始...")
            if page_count > END_PAGE:
                print(f"指定された終了ページ（{END_PAGE}P）に達したため、処理を正常終了します。")
                break

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
                except:
                    continue

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
                    except NoSuchElementException:
                        pass

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
                            except NoSuchElementException:
                                pass
                    except Exception:
                        pass

                    phone = None
                    if found_hp_url and "tsukulink.net" not in found_hp_url:
                        phone = deep_scan_external_site(driver, found_hp_url)
                    
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
                print("\n「次へ」ボタンが見つからないか、最終ページに到達しました。終了します。")
                break

    finally:
        print("\n==========================================")
        print(" 処理終了フェーズ：Slackへファイルを送信します")
        print("==========================================")
        
        # 🟢 【新機能】全ページ終了後に、完成したCSVファイルをSlackへドカンとアップロード
        upload_to_slack(
            file_path=OUTPUT_MOBILE, 
            comment=f"✅ 【採掘完了】{TARGET_PREFECTURE} ({START_PAGE}P～{END_PAGE}P) の [携帯番号リスト] です！ (総抽出: {total_extracted_count}件)"
        )
        upload_to_slack(
            file_path=OUTPUT_OTHER, 
            comment=f"✅ 【採掘完了】{TARGET_PREFECTURE} ({START_PAGE}P～{END_PAGE}P) の [固定電話・その他リスト] です！"
        )
        
        driver.quit()


if __name__ == "__main__":
    scrape_tsukulink()
