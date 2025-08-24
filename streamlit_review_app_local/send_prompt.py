import sys
import time
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver import ActionChains

def send_to_gemini(prompt: str):
    driver = None
    try:
        # 1) ChromeDriver 자동 설치 + 실행
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install())
        )
        # 2) Gemini 앱 접속
        driver.get("https://gemini.google.com/app")
        print("→ Gemini 페이지 열림, 로그인 완료 후 기다려 주세요.")

        # 3) 에디터 로드 대기
        wait = WebDriverWait(driver, 15)
        editor = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.ql-editor"))
        )

        # 4) 더블클릭으로 포커스
        ActionChains(driver).double_click(editor).perform()

        # 5) JS로 한 번에 텍스트 입력 (send_keys 대신)
        driver.execute_script(
            "arguments[0].innerText = arguments[1];",
            editor,
            prompt
        )
        print("✅ 프롬프트 입력 완료. 결과를 확인하세요.")
        
        # 6) 잠시 대기
        time.sleep(60)

    except Exception as e:
        print(f"❌ 자동화 오류: {e}")
    # 브라우저는 닫지 않고 그대로 남겨둡니다.

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python send_prompt.py \"<your prompt here>\"")
        sys.exit(1)
    # 따옴표 처리된 prompt를 받아옵니다.
    prompt_text = sys.argv[1]
    send_to_gemini(prompt_text)
