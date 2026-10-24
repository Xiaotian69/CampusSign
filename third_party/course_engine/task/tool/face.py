"""Wait for official manual verification; never alter verification elements."""
import time

def delete_face_popup(driver, pass_face=False, class_name=None):
    from selenium.webdriver.common.by import By
    selectors = ".faceCollectQrPop, .chapterVideoFaceQrMaskDiv, .faceRecognition, #faceRecognition"
    announced = False
    deadline = time.monotonic() + 600
    while any(element.is_displayed() for element in driver.find_elements(By.CSS_SELECTOR, selectors)):
        if not announced:
            print("请在官方页面或手机端完成身份验证，程序正在等待。", flush=True)
            announced = True
        if time.monotonic() >= deadline:
            raise TimeoutError("等待官方身份验证超时")
        time.sleep(1)
