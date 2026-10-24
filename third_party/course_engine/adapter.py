"""CampusSign adapter. Selenium imports remain lazy for the base sign-in app."""
import time
from urllib.parse import urlparse


def create_driver(config):
    from selenium import webdriver
    if config["browser"] == "chrome":
        from selenium.webdriver.chrome.service import Service
        options = webdriver.ChromeOptions()
        constructor = webdriver.Chrome
    else:
        from selenium.webdriver.edge.service import Service
        options = webdriver.EdgeOptions()
        constructor = webdriver.Edge
    service = Service(config["driver_path"]) if config["driver_path"] else Service()
    driver = constructor(service=service, options=options)
    driver.implicitly_wait(2)
    return driver


def login(driver, config):
    from selenium.webdriver.common.by import By
    driver.get("https://i.chaoxing.com/")
    if config["login_mode"] == "account":
        try:
            account = config["account"]
            driver.find_element(By.ID, "phone").send_keys(account["uname"])
            driver.find_element(By.ID, "pwd").send_keys(account["password"])
            driver.find_element(By.ID, "loginBtn").click()
        except Exception:
            print("请在浏览器完成学校账号登录或扫码登录。", flush=True)
    else:
        print("请在浏览器选择官方二维码并扫码登录。", flush=True)
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        host = urlparse(driver.current_url).hostname or ""
        if host == "i.chaoxing.com" and any(c.get("name") in ("_uid", "UID", "UID2") for c in driver.get_cookies()):
            print("官方页面登录成功。", flush=True)
            return
        time.sleep(1)
    raise TimeoutError("等待登录超时")


def run(config):
    driver = create_driver(config)
    try:
        login(driver, config)
        from . import navigation as nav
        from .task.tool.DeepSeekAsk import configure
        from .task.do_work import do_work
        configure(config["ai_model"])
        for course in config["courses"]:
            print("正在处理课程：" + course, flush=True)
            driver.get("https://i.chaoxing.com/")
            nav.error_num = 0
            nav.delete_record()
            nav.choice_course(driver, course, config["speed"], "作业" if config["task_type"] == "作业" else "章节", config["account"].get("uname", "qr"))
            if not nav.turn_page(driver, course):
                raise RuntimeError("未找到课程页面")
            nav.experience(driver)
            nav.delete_face_popup(driver)
            if nav.find_mission(driver, "作业" if config["task_type"] == "作业" else "章节", config["speed"], course):
                if config["task_type"] == "作业":
                    do_work(driver, course, config["homework"], config["api_key"] if config["choice"] == "DeepSeek AI" else "", config["choice"])
                else:
                    if not nav.turn_page(driver, "学生学习页面"):
                        raise RuntimeError("未找到学习页面")
                    nav.delete_face_popup(driver)
                    nav.fold(driver)
                    nav.run(driver, config["choice"], course, config["api_key"], config["lock_screen"], False, config["choice"] if config["choice"] != "不刷题" else "手动答题", config["discussion_choice"], config["after_finish_question"], False, config["speed"], False)
            print("课程处理结束：" + course, flush=True)
    finally:
        try:
            driver.quit()
        finally:
            if config.get("lock_screen"):
                import os
                if os.name == "nt":
                    import ctypes
                    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
