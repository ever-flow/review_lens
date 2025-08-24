import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

# --- 크롤링 함수들 정의 시작 ---
MAX_REVIEWS = 100
CLICK_BATCH = 10

def init_driver(headless=False):
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=ko")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-allow-origins=*")  # 필수 옵션
    if headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)



# --- Kakao Map Functions ---
def crawl_kakao_reviews(restaurant_name):
    driver = init_driver(headless=False)
    print(f"[Kakao] '{restaurant_name}' 검색 시작")
    try:
        driver.get("https://map.kakao.com/")
        wait = WebDriverWait(driver, 10)

        # 검색어 입력
        box = wait.until(EC.presence_of_element_located((By.ID, "search.keyword.query")))
        box.send_keys(restaurant_name, Keys.RETURN)
        print("[Kakao] 검색어 전송 완료")
        time.sleep(2)

        # dimmedLayer 제거 후 '더보기' 클릭 시도
        try:
            dimmed = driver.find_element(By.ID, "dimmedLayer")
            if dimmed.is_displayed():
                driver.execute_script("arguments[0].style.display = 'none';", dimmed)
                print("[Kakao] dimmedLayer 제거 완료")
        except NoSuchElementException:
            pass

        # 첫 번째 장소 상세 페이지 이동
        place = wait.until(EC.presence_of_element_located((By.XPATH, '//*[@id="info.search.place.list"]/li[1]')))
        btn = place.find_element(By.CLASS_NAME, "moreview")
        driver.execute_script("arguments[0].click();", btn)
        print("[Kakao] 상세 페이지로 이동")

        # 새 창 전환
        main = driver.window_handles[0]
        WebDriverWait(driver, 10).until(lambda d: len(d.window_handles) == 2)
        detail = [h for h in driver.window_handles if h != main][0]
        driver.switch_to.window(detail)
        print("[Kakao] 상세 창 포커스 전환")

        # ──────────────────────────────────────────────────────────────────
        # ★ 실제 표시된 식당 이름 추출
        try:
            # Kakao 페이지의 식당명 요소(=상단에 크게 나오는 제목)를 찾습니다.
            name_elem = wait.until(EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#mainContent > div.top_basic > div.info_main > div.unit_info > h3") ))
            actual_name = name_elem.text.strip()
        except Exception:
            actual_name = restaurant_name
        print(f"[Kakao] 실제 식당 이름: {actual_name}")
        # ──────────────────────────────────────────────────────────────────


        # 리뷰 탭 클릭 시도
        try:
            review_tab = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//a[@class='link_tab' and contains(text(), '후기')]")
            ))
            driver.execute_script("arguments[0].click();", review_tab)
            print("[Kakao] 리뷰 탭 클릭 완료")
            time.sleep(1)
        except TimeoutException:
            print("[Kakao] 리뷰 탭('후기')이 존재하지 않음 → 리뷰 없음으로 처리")
            return []

        # 리뷰 리스트 로딩 확인
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.list_review")))
            time.sleep(1)

            items = driver.find_elements(By.CSS_SELECTOR, "ul.list_review > li")
            items = items[:MAX_REVIEWS]

            reviews = []
            for idx, item in enumerate(items):
                try:
                    # 본문 더보기 클릭
                    try:
                        btn_more = item.find_element(By.CSS_SELECTOR, "span.btn_more")
                        driver.execute_script("arguments[0].click();", btn_more)
                        time.sleep(0.3)
                    except NoSuchElementException:
                        pass

                    # reviewer 추출
                    name_elem = item.find_element(By.CSS_SELECTOR, "span.name_user")
                    raw_name = name_elem.text.split(",")[-1].strip()
                    reviewer = raw_name

                    # rating 추출
                    rating_elem = item.find_element(
                        By.CSS_SELECTOR,
                        "span.starred_grade > span.screen_out:nth-of-type(2)"
                    )
                    rating = rating_elem.text.strip()

                    area = item.find_element(By.CLASS_NAME, "area_review")
                    text = area.find_element(By.CLASS_NAME, "desc_review").text.strip()
                    date = area.find_element(By.CLASS_NAME, "txt_date").text.strip()

                    # ─────────────────────────────────────────────────────────
                    # ★ 리뷰 딕셔너리에 actual_name을 추가
                    reviews.append({
                        'platform': 'Kakao',
                        'restaurant_name': actual_name,   # <<< 실제 식당 이름 필드
                        'reviewer': reviewer,
                        'text': text,
                        'rating': rating,
                        'date': date
                    })
                    # ─────────────────────────────────────────────────────────

                    print(f"[Kakao] 리뷰 {idx + 1} 수집 완료")
                except Exception as review_error:
                    print(f"[Kakao] 리뷰 {idx + 1} 수집 실패: {review_error}")
                    continue

            print(f"[Kakao] 리뷰 수집 완료: {len(reviews)}개")
            return reviews

        except Exception as e:
            print(f"[Kakao] 리뷰 리스트 로딩 실패: {type(e).__name__} - {e}")
            return []

    except Exception as e:
        print(f"[Kakao] 오류 발생: {e}")
        return []

    finally:
        driver.quit()


# --- Google Maps Helper Functions ---
def click_review_tab(driver):
    """리뷰 탭을 찾아 클릭합니다."""
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, 'button[role="tab"]')
        for t in tabs:
            if "리뷰" in t.text:
                try:
                    t.click()
                except:
                    driver.execute_script("arguments[0].click();", t)
                WebDriverWait(driver, 5).until(
                    lambda d: t.get_attribute("aria-selected") == "true"
                )
                print("[Google] 리뷰 탭 클릭 완료")
                time.sleep(0.5)
                return True
        print("[Google] 리뷰 탭을 찾지 못함")
        return False
    except Exception as e:
        print(f"[Google] 리뷰 탭 클릭 중 오류: {e}")
        return False


def get_top_reviews(driver, place_name, topn=MAX_REVIEWS, max_scrolls=12):
    """리뷰 패널에서 최대 topn개의 리뷰를 수집하고, 각 리뷰에 place_name을 함께 포함합니다."""
    try:
        panel = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf"))
        )
        print("[Google] 리뷰 패널 로딩 완료")
    except TimeoutException:
        print("[Google] 리뷰 패널 로딩 실패: 패널을 찾을 수 없음")
        return []

    seen_ids = set()
    reviews = []
    prev_block_count = 0

    for i in range(max_scrolls):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", panel)
        time.sleep(2.5)

        blocks = panel.find_elements(By.CSS_SELECTOR, 'div.jftiEf')
        print(f"[Google] 스크롤 {i+1}: {len(blocks)}개의 리뷰 블록 발견")

        for blk in blocks:
            rid = blk.get_attribute("data-review-id")
            if not rid or rid in seen_ids:
                continue

            text_elements = blk.find_elements(By.CSS_SELECTOR, "span.wiI7pd")
            if not text_elements:
                continue

            try:
                seen_ids.add(rid)
                writer = blk.find_element(By.CSS_SELECTOR, "div.d4r55").text.strip()
                text   = text_elements[0].text.replace("\n", " ").strip()
                star   = blk.find_element(By.CSS_SELECTOR, "span.kvMYJc").get_attribute("aria-label").strip()
                date   = blk.find_element(By.CSS_SELECTOR, "span.rsqaWe").text.strip()

                # ★ 리뷰 딕셔너리에 place_name(=실제 식당 이름)을 추가
                reviews.append({
                    'platform': 'Google',
                    'restaurant_name': place_name,
                    'reviewer': writer,
                    'text': text,
                    'rating': star,
                    'date': date
                })
                print(f"[Google] 리뷰 수집: 작성자={writer}, 평점={star}")
            except Exception as e:
                print(f"[Google] 리뷰 블록 처리 중 오류: {e}")
                continue

            if len(reviews) >= topn:
                print(f"[Google] 목표 리뷰 수({topn}) 도달")
                return reviews

        if len(blocks) == prev_block_count:
            print("[Google] 더 이상 새로운 리뷰 블록 없음 (종료)")
            break
        prev_block_count = len(blocks)

    print(f"[Google] 총 {len(reviews)}개 리뷰 수집 완료")
    return reviews


# --- Google Maps Crawling Function ---
def crawl_google_reviews(restaurant_name):
    driver = init_driver(headless=False)
    print(f"[Google] '{restaurant_name}' 검색 시작")
    try:
        driver.get("https://www.google.com/maps")
        wait = WebDriverWait(driver, 10)
        inp = wait.until(EC.presence_of_element_located((By.ID, "searchboxinput")))
        inp.clear()
        inp.send_keys(restaurant_name)
        inp.send_keys(Keys.ENTER)

        # 검색 결과 로딩 대기
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.Nv2PK.THOPZb.CpccDe"))
            )
            print("[Google] 검색 결과 로딩 완료")
        except TimeoutException:
            print("[Google] 검색 결과 로딩 실패: 결과 카드 없음")

        # 첫 번째 검색 결과 카드 찾기
        href = None
        try:
            card = driver.find_element(By.CSS_SELECTOR, "div.Nv2PK.THOPZb.CpccDe")
            a = card.find_element(By.CSS_SELECTOR, "a.hfpxzc")
            href = a.get_attribute("href")
            print("[Google] 첫 번째 결과 카드 찾음 → 상세 페이지 이동")
        except NoSuchElementException:
            print("[Google] 첫 번째 결과 카드 찾기 실패 → 현재 URL로 상세 페이지 이동 시도")
            href = driver.current_url

        # 상세 페이지로 이동
        driver.get(href)
        # 상세 페이지 로딩 완료 시점을 <h1> 태그로 판단
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        print("[Google] 상세 페이지 로딩 완료")

        # ──────────────────────────────────────────────────────────────────
        # ★ 여기서 실제 표시되는 식당(장소) 이름을 꺼내서 place_name에 저장
        try:
            place_name = driver.find_element(By.TAG_NAME, "h1").text.strip()
        except:
            place_name = restaurant_name
        print(f"[Google] 실제 장소 이름: {place_name}")
        # ──────────────────────────────────────────────────────────────────

        # 리뷰 탭 클릭
        if not click_review_tab(driver):
            print("[Google] 리뷰 탭을 찾지 못함")
            return []

        # 실제 place_name을 넘겨 주며 리뷰 수집
        reviews = get_top_reviews(driver, place_name, topn=MAX_REVIEWS)
        print(f"[Google] 리뷰 수집 완료: {len(reviews)}개")
        return reviews

    except Exception as e:
        print(f"[Google] 오류 발생: {e}")
        return []

    finally:
        driver.quit()


# --- Naver Map Functions ---
def crawl_reviews(driver, section, actual_restaurant_name, max_reviews=MAX_REVIEWS):
    """
    "더보기" 버튼을 반복 클릭해 지정된 개수만큼 리뷰를 로드하고,
    리뷰 텍스트, 날짜, 그리고 actual_restaurant_name을 함께 반환합니다.
    """
    clicks = 0
    # 반복 클릭하여 더 많은 리뷰 로드
    while True:
        items = section.find_elements(By.CSS_SELECTOR, "ul > li")
        if len(items) >= max_reviews:
            break
        try:
            more_btn = section.find_element(By.XPATH, ".//a[.//span[text()='더보기']]")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", more_btn)
            driver.execute_script("arguments[0].click();", more_btn)
            clicks += 1
            time.sleep(1)
        except (NoSuchElementException, TimeoutException):
            break

    # 로드된 리뷰 요소 재획득
    items = section.find_elements(By.CSS_SELECTOR, "ul > li")
    reviews = []
    for idx, item in enumerate(items[:max_reviews], start=1):
        try:
            author = item.find_element(By.CSS_SELECTOR, "div.pui__JiVbY3 span span").text
            date_elem = item.find_element(By.TAG_NAME, "time")
            date = date_elem.get_attribute("datetime") or date_elem.text.strip()
            text = item.find_element(By.CSS_SELECTOR, "div.pui__vn15t2 > a").text
            reviews.append({
                'platform': 'Naver',
                'restaurant_name': actual_restaurant_name,  # 식당 이름 같이 수집
                'reviewer': author,
                'text': text,
                'rating': None,
                'date': date
            })
            print(f"[Naver] 리뷰 {idx} 수집 완료: 작성자={author}, 날짜={date}")
        except NoSuchElementException:
            print(f"[Naver] 리뷰 {idx} 수집 실패: 요소 누락")
            continue
    print(f"[Naver] 리뷰 수집 완료: {len(reviews)}개")
    return reviews


def crawl_naver_reviews(restaurant_name):
    """
    주어진 식당 이름으로 Naver Map v5에서 리뷰를 최대 MAX_REVIEWS개까지 수집합니다.
    """
    driver = init_driver()
    wait = WebDriverWait(driver, 15)
    print(f"[Naver] '{restaurant_name}' 검색 시작")
    try:
        driver.get("https://map.naver.com/v5")
        time.sleep(2)
        # 오버레이 제거
        driver.execute_script(
            "document.querySelectorAll('div.modal_layer, div.dimmedLayer').forEach(el => el.style.display='none');"
        )
        # 검색어 입력
        try:
            sb = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.input_search")))
        except TimeoutException:
            sb = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder*='장소']")))
        sb.clear()
        sb.send_keys(restaurant_name, Keys.ENTER)
        print("[Naver] 검색어 전송 완료")
        time.sleep(2)

        # searchIframe으로 전환
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#searchIframe")))
        time.sleep(1)
        first_li = wait.until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "#_pcmap_list_scroll_container > ul > li:nth-child(1)"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", first_li)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", first_li.find_element(By.TAG_NAME, "a"))
        print("[Naver] 첫 번째 결과 클릭 완료")
        time.sleep(2)

        # entryIframe으로 돌아와서
        driver.switch_to.default_content()
        wait.until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, "iframe#entryIframe")))
        time.sleep(1)

        # ────────────────────────────────────────────────────────────────
        # ★ 실제 페이지에 표시된 “식당 이름”을 가져올 셀렉터를 여기에 넣습니다.
        try:
            name_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#_title > div > span.GHAhO")))
            actual_restaurant_name = name_elem.text.strip()
        except Exception:
            # 셀렉터가 맞지 않으면, 입력받은 restaurant_name 사용
            actual_restaurant_name = restaurant_name
        print(f"[Naver] 실제 식당 이름: {actual_restaurant_name}")
        # ────────────────────────────────────────────────────────────────

        # 리뷰 탭 클릭
        review_tab = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[.//span[text()='리뷰']]") )
        )
        driver.execute_script("arguments[0].click();", review_tab)
        print("[Naver] 리뷰 탭 클릭 완료")
        time.sleep(1)

        # 리뷰 섹션 로딩 및 수집
        section = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.place_section.k1QQ5")))
        return crawl_reviews(driver, section, actual_restaurant_name)

    except Exception as e:
        print(f"[Naver] 오류 발생: {e}")
        return []
    finally:
        driver.quit()

# --- 크롤링 함수들 정의 끝 ---
