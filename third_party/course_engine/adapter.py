"""CampusSign adapter. Selenium imports remain lazy for the base sign-in app."""
import time
from urllib.parse import urlparse

BROWSER_NAMES = {"edge": "微软 Edge", "chrome": "谷歌 Chrome"}


class BrowserStartError(RuntimeError):
    """Browser or driver could not be started; message is safe to show."""


def _create(browser, driver_path):
    from selenium import webdriver
    if browser == "chrome":
        from selenium.webdriver.chrome.service import Service
        options = webdriver.ChromeOptions()
        constructor = webdriver.Chrome
    else:
        from selenium.webdriver.edge.service import Service
        options = webdriver.EdgeOptions()
        constructor = webdriver.Edge
    service = Service(driver_path) if driver_path else Service()
    driver = constructor(service=service, options=options)
    driver.implicitly_wait(2)
    return driver


def create_driver(config):
    """Start the chosen browser; "auto" tries Edge first, then Chrome."""
    from selenium.common import WebDriverException
    browsers = ["edge", "chrome"] if config["browser"] == "auto" else [config["browser"]]
    failures = []
    for browser in browsers:
        print("正在启动" + BROWSER_NAMES[browser] + "（首次使用可能需要联网下载驱动）…", flush=True)
        try:
            return _create(browser, config.get("driver_path", ""))
        except WebDriverException as exc:
            failures.append(BROWSER_NAMES[browser] + "：" + type(exc).__name__)
    raise BrowserStartError("无法启动浏览器（" + "；".join(failures) + "）。请确认已安装该浏览器、"
                            "网络可以下载驱动，或在高级设置中更换浏览器/指定驱动路径。")


def logged_in(driver):
    host = urlparse(driver.current_url).hostname or ""
    return host == "i.chaoxing.com" and any(c.get("name") in ("_uid", "UID", "UID2") for c in driver.get_cookies())


def login(driver, config, timeout=600):
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
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if logged_in(driver):
            print("官方页面登录成功。", flush=True)
            return
        time.sleep(1)
    raise TimeoutError("等待登录超时")


def list_courses(driver):
    """Read course titles from "我学的课"; return [] when the page cannot be read."""
    from selenium.webdriver.common.by import By
    names = []
    try:
        driver.get("https://i.chaoxing.com/")
        for selector in ('[title="新泛雅"]', '[title*="课程"]'):
            found = driver.find_elements(By.CSS_SELECTOR, selector)
            if found:
                driver.execute_script("arguments[0].click();", found[0])
                break
        time.sleep(3)
        try:
            driver.switch_to.frame("frame_content")
        except Exception:
            pass
        for selector in (".course-name", ".courseName", '[class="w_cour_txtH fl"]'):
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                name = (element.get_attribute("title") or element.text or "").strip()
                if name and name not in names:
                    names.append(name)
            if names:
                break
    except Exception as exc:
        print("读取课程列表失败（" + type(exc).__name__ + "），可手动输入课程名。", flush=True)
    finally:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
    return names


def browser_alive(driver):
    try:
        return bool(driver.window_handles)
    except Exception:
        return False


def run_course(driver, config, course):
    from . import navigation as nav
    from .task.do_work import do_work
    print("正在处理课程：" + course, flush=True)
    driver.get("https://i.chaoxing.com/")
    nav.error_num = 0
    nav.delete_record()
    nav.choice_course(driver, course, config["speed"], "作业" if config["task_type"] == "作业" else "章节", config["account"].get("uname") or "qr")
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


def run_courses(driver, config, keep_going=False):
    """Process courses in order. With keep_going, one failed course does not stop the queue.

    Returns [(course, outcome)], outcome is "已遍历" or "失败：<reason>". "已遍历" only means
    the queue reached the end of that course, not that the platform recorded completion.
    """
    from .task.tool.DeepSeekAsk import configure
    configure(config["ai_model"])
    results = []
    for course in config["courses"]:
        try:
            run_course(driver, config, course)
            results.append((course, "已遍历"))
        except Exception as exc:
            if not keep_going or not browser_alive(driver):
                raise
            reason = str(exc) if isinstance(exc, (RuntimeError, TimeoutError)) and str(exc) else type(exc).__name__
            print("课程处理失败：" + course + "（" + reason + "）", flush=True)
            results.append((course, "失败：" + reason))
    return results


def release_keep_awake(config):
    if config.get("lock_screen"):
        import os
        if os.name == "nt":
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


def run(config):
    driver = create_driver(config)
    try:
        login(driver, config)
        run_courses(driver, config)
    finally:
        try:
            driver.quit()
        finally:
            release_keep_awake(config)
