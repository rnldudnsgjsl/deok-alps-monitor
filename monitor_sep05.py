# -*- coding: utf-8 -*-
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BOOKING_URL = "https://camping.ulju.ulsan.kr/ujcamping/campsite/booking"
TARGET_DATE = "2026-09-05"
TARGET_SITES = [44, 45, 46, 47, 48]

AVAILABLE_WORDS = ("예약가능", "예약 가능", "예약하기", "신청가능", "신청 가능", "가능")
UNAVAILABLE_WORDS = ("예약완료", "예약 완료", "예약불가", "예약 불가", "마감", "이용불가", "대기", "불가")

def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()

def log(msg):
    print(f"[{datetime.now(ZoneInfo('Asia/Seoul')).strftime('%Y-%m-%d %H:%M:%S KST')}] {msg}", flush=True)

def ntfy_send(topic, title, message):
    r = requests.post(
        f"https://ntfy.sh/{topic.strip()}",
        data=f"{title}\n{message}".encode("utf-8"),
        headers={
            "Priority": "urgent",
            "Tags": "camping,tada",
            "Click": BOOKING_URL,
        },
        timeout=20,
    )
    r.raise_for_status()

def make_driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1600,1000")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--lang=ko-KR")
    return webdriver.Chrome(options=opts)

def result_rows(driver):
    rows = []
    for tr in driver.find_elements(By.XPATH, "//table//tr"):
        try:
            if tr.is_displayed():
                txt = norm(tr.text)
                if txt:
                    rows.append(txt)
        except Exception:
            pass
    return rows

def selected_date_has_results(driver):
    body = norm(driver.find_element(By.TAG_NAME, "body").text)
    # If today's closing notice is shown, target date was not successfully selected.
    if "당일(" in body and "예약은 17시에 마감되었습니다" in body:
        return False
    return len(result_rows(driver)) >= 2

def exact_text_candidates(driver, text, left_side=None):
    candidates = []
    for xp in [
        f"//*[normalize-space(text())='{text}']",
        f"//*[normalize-space(.)='{text}']",
    ]:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if not el.is_displayed():
                    continue
                r = el.rect
                if r.get("width", 0) <= 0 or r.get("height", 0) <= 0:
                    continue
                if left_side is not None:
                    win_w = driver.execute_script("return window.innerWidth")
                    is_left = (r.get("x", 0) + r.get("width", 0) / 2) < win_w * 0.55
                    if is_left != left_side:
                        continue
                candidates.append(el)
        except Exception:
            pass

    uniq, seen = [], set()
    for el in candidates:
        try:
            key = (
                round(el.rect["x"]), round(el.rect["y"]),
                round(el.rect["width"]), round(el.rect["height"])
            )
        except Exception:
            continue
        if key not in seen:
            seen.add(key)
            uniq.append(el)
    uniq.sort(key=lambda e: e.rect.get("width", 9999) * e.rect.get("height", 9999))
    return uniq

def select_aug22(driver):
    candidates = exact_text_candidates(driver, "22", left_side=True)
    log(f"22일 후보 수: {len(candidates)}")

    for ci, el in enumerate(candidates[:10], start=1):
        try:
            if el.rect["y"] < 250:
                continue
        except Exception:
            pass

        targets = [el]
        cur = el
        for _ in range(4):
            try:
                cur = cur.find_element(By.XPATH, "..")
                if cur.is_displayed():
                    targets.append(cur)
            except Exception:
                break

        for ti, target in enumerate(targets, start=1):
            try:
                r = target.rect
                if r.get("width", 0) > 350 or r.get("height", 0) > 220:
                    continue
                driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center',inline:'center'});",
                    target,
                )
                time.sleep(0.15)
                try:
                    ActionChains(driver).move_to_element(target).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", target)
                time.sleep(1.3)
                if selected_date_has_results(driver):
                    log(f"8월 22일 선택 성공: 후보 {ci}, 단계 {ti}")
                    return True
            except Exception:
                continue

    # coordinate fallback
    try:
        if candidates:
            c22 = candidates[0]
            x = c22.rect["x"] + c22.rect["width"] / 2
            y = c22.rect["y"] + c22.rect["height"] / 2
            for dx, dy in [(0, 0), (10, 10), (-10, 10), (0, 25)]:
                driver.execute_script(
                    "const t=document.elementFromPoint(arguments[0],arguments[1]);"
                    "if(t){t.click(); return true;} return false;",
                    x + dx, y + dy,
                )
                time.sleep(1.2)
                if selected_date_has_results(driver):
                    log("8월 22일 좌표 클릭 성공")
                    return True
    except Exception:
        pass

    return False

def table_is_deok(driver):
    return any("등억알프스야영장" in row for row in result_rows(driver))

def select_deok(driver):
    if table_is_deok(driver):
        return True

    candidates = exact_text_candidates(driver, "등억알프스야영장", left_side=False)
    log(f"등억알프스 텍스트 후보 수: {len(candidates)}")

    for ci, el in enumerate(candidates[:10], start=1):
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center',inline:'center'});", el
            )

            try:
                ActionChains(driver).move_to_element(el).click().perform()
            except Exception:
                driver.execute_script("arguments[0].click();", el)

            time.sleep(1.5)
            if table_is_deok(driver):
                log(f"등억알프스 직접 클릭 성공: 후보 {ci}")
                return True

            box = el.rect
            cy = box["y"] + box["height"] / 2

            for gap in (10, 18, 24, 30, 36):
                px = max(1, box["x"] - gap)
                py = cy
                try:
                    driver.execute_script(
                        "const t=document.elementFromPoint(arguments[0],arguments[1]);"
                        "if(t){t.click(); return true;} return false;",
                        px, py,
                    )
                except Exception:
                    pass
                time.sleep(1.2)
                if table_is_deok(driver):
                    log(f"등억알프스 좌표 클릭 성공: 후보 {ci}, gap {gap}")
                    return True

            cur = el
            for level in range(1, 5):
                try:
                    cur = cur.find_element(By.XPATH, "..")
                    txt = norm(cur.text)
                    if "등억알프스야영장" not in txt:
                        continue
                    if cur.rect.get("width", 0) > 350:
                        continue
                    for radio in cur.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
                        try:
                            driver.execute_script("arguments[0].click();", radio)
                            time.sleep(1.5)
                            if table_is_deok(driver):
                                log(f"등억알프스 parent-radio 성공: 후보 {ci}, 부모 {level}")
                                return True
                        except Exception:
                            pass
                except Exception:
                    break
        except Exception:
            pass

    return False

def scan_sites(driver):
    available = set()
    details = {}
    rows = result_rows(driver)

    if not any("등억알프스야영장" in row for row in rows):
        return available, {s: "" for s in TARGET_SITES}

    for site in TARGET_SITES:
        pat = re.compile(rf"(?<!\d){site}(?:번)?(?!\d)")
        matched = [row for row in rows if "등억알프스야영장" in row and pat.search(row)]
        merged = " | ".join(matched)
        details[site] = merged

        if merged:
            if any(w in merged for w in UNAVAILABLE_WORDS):
                is_available = False
            else:
                is_available = any(w in merged for w in AVAILABLE_WORDS)
            if is_available:
                available.add(site)

    return available, details

def main():
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        log("ERROR: GitHub Secret NTFY_TOPIC이 설정되지 않았습니다.")
        sys.exit(2)

    # 수동 실행은 1회만 검사.
    # Scheduled 실행은 5분 간격으로 반복 검사.
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    repeat_count = 1 if event_name == "workflow_dispatch" else 13

    last_available = set()

    for check_no in range(1, repeat_count + 1):
        started = time.monotonic()

        now_kst = datetime.now(ZoneInfo("Asia/Seoul"))

        if (
            now_kst.year != 2026
            or now_kst.month != 8
            or now_kst.day > 22
        ):
            log("감시 기간 밖입니다. 종료합니다.")
            return

        log(f"===== 확인 {check_no}/{repeat_count} 시작 =====")

        driver = None

        try:
            driver = make_driver()

            driver.get(BOOKING_URL)

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            time.sleep(1.5)

            if not select_aug22(driver):
                log("ERROR: 8월 22일 선택 실패")
                continue

            if not select_deok(driver):
                log("ERROR: 등억알프스야영장 선택/검증 실패")
                continue

            available, details = scan_sites(driver)

            for site in TARGET_SITES:
                if details.get(site):
                    log(f"{site}번: {details[site]}")

            if available:
                nums = ", ".join(
                    f"{x}번" for x in sorted(available)
                )

                log(f"예약 가능 발견: {nums}")

                new_sites = available - last_available

                if new_sites:
                    new_nums = ", ".join(
                        f"{x}번" for x in sorted(new_sites)
                    )

                    ntfy_send(
                        topic,
                        "등억알프스 빈자리 발견!",
                        f"2026-08-22 / {new_nums} 예약 가능으로 감지\n"
                        "알림을 눌러 예약페이지를 확인하세요.",
                    )

                    log(f"휴대폰 알림 전송: {new_nums}")

            else:
                log("44~48번 빈자리 없음")

            last_available = set(available)

        except Exception as e:
            log(f"ERROR: {type(e).__name__}: {e}")

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

        # 마지막 확인이 아니면 5분 간격 유지
        if check_no < repeat_count:
            elapsed = time.monotonic() - started
            wait_seconds = max(0, 300 - elapsed)

            log(
                f"다음 확인까지 약 {wait_seconds:.0f}초 대기"
            )

            time.sleep(wait_seconds)


if __name__ == "__main__":
    main()
