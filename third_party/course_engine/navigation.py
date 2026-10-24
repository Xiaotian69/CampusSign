# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.

#打包python -m PyInstaller --onefile --collect-all selenium main.py
import json
import re
import time
import traceback
from selenium.common import NoSuchDriverException, NoSuchWindowException, WebDriverException, \
    ElementNotInteractableException, SessionNotCreatedException, NoSuchElementException, \
    ElementClickInterceptedException
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium import webdriver

from third_party.course_engine.task.tool.common import save_process
from third_party.course_engine.task.tool.face import delete_face_popup
from third_party.course_engine.task.finish_dicussion import finish_discussion
from third_party.course_engine.task.play_audio import play_audio
from third_party.course_engine.task.tool import color
from third_party.course_engine.task.watch_live import watch_live
from third_party.course_engine.task.watch_ppt import __ppt
from third_party.course_engine.task.watch_vido import study_page
from third_party.course_engine.task.quiz_ai import  finish_quiz
from third_party.course_engine.task.tool.send_wx import send_error
from third_party.course_engine.task.do_work import do_work
from third_party.course_engine.task.reading import reading
condition=True#用于判断是否调节倍数
error_num=0#错误次数
def save_course_lst(driver,class_name,course_elements,phone_number):
    try:
        have_task_course_element=driver.find_element(By.ID,'stuNormalCourseListDiv')
    except:
        have_task_course_element=driver
    try:
        new_course_elements=have_task_course_element.find_elements(By.CSS_SELECTOR, f'[class*="{class_name}"]')
        if len(new_course_elements)!=0:
            course_elements=new_course_elements
        course_list = [course_element.get_attribute('title') for course_element in course_elements if
                       course_element.get_attribute('title')!= '']
        if len(course_list)==0:
            course_list=[course_element.text for course_element in new_course_elements if
                       course_element.text!= '']
        if len(course_list) == 0:
            print(color.red(f'获取课程列表失败'), flush=True)
        else:
            try:
                with open(r'task/tool/course_name.json', 'r', encoding='utf-8') as f:
                    dit = json.load(f)
                with open(r'task/tool/course_name.json', 'w', encoding='utf-8') as f:
                    new_list = dit.get(phone_number,[]) + course_list
                    # 去重
                    new_list = list(set(new_list))
                    dit[phone_number]=new_list
                    json.dump(dit, f, ensure_ascii=False, indent=2)
                print(color.green(f'保存课程列表成功,共有{len(new_list)}个课程'), flush=True)
            except:
                print(color.red('保存课程列表失败'), flush=True)
    except:
        print(color.red('保存课程列表失败'), flush=True)

def experience(driver):
    # 体验最新版本
    try:
        element = driver.find_element(By.CLASS_NAME, 'experience')
        time.sleep(1)
        element.click()
        print(color.green('正在体验最新版本'), flush=True)
    except NoSuchElementException:
        pass

def choice_course(driver, course_name,speed,task_type,phone_number):
    # time.sleep(200)
    """
    选择指定名称的课程

    参数:
    driver: WebDriver 对象，用于控制浏览器
    course_name: 字符串，要选择的课程名称

    返回:
    无
    """
    # 点击课程
    try:
        driver.find_element(By.CSS_SELECTOR, '[title="新泛雅"]').click()
        time.sleep(1)
    except:
        try:
            element = driver.find_element(By.CSS_SELECTOR, '[title*="课程"]')
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            time.sleep(0.5)  # 稍等滚动动画完成
            element.click()
            time.sleep(1)
        except NoSuchElementException:
            try:
                driver.find_element(By.CSS_SELECTOR, '[title*="首页"]').click()
                time.sleep(1)
            except:
                pass
    try:
        time.sleep(3)
        driver.switch_to.frame('frame_content')

        # 选择‘我的课程’并点击
        element = driver.find_element(By.CLASS_NAME, 'course-tab')
        elements = element.find_elements(By.TAG_NAME, 'div')
        for element in elements:
            if element.text == '我学的课':
                element.click()
                break
        element.click()
        time.sleep(1)
    except:
        pass
    try:
        print(color.green(f'正在定位《{course_name}》...'),flush=True)
        # experience(driver)
        # turn_page(driver,'课程')
        # 查找所有课程名称元素
        course_elements = driver.find_elements(By.CLASS_NAME, "course-name")
        class_name = "course-name"
        if len(course_elements) == 0:
            course_elements = driver.find_elements(By.CLASS_NAME, 'courseName')
            class_name = "courseName"
        if len(course_elements) == 0:
            # turn_page(driver, '个人空间')
            # driver.switch_to.frame('frame_content')
            course_elements = driver.find_elements(By.CSS_SELECTOR, '[class="w_cour_txtH fl"]')
            class_name="w_cour_txtH fl"
        save_course_lst(driver,class_name,course_elements,phone_number)
        # 遍历所有课程元素
        for course_element in course_elements:
            # 如果课程元素的标题属性与指定的课程名称匹配
            if  course_name in course_element.get_attribute('title') or course_name in course_element.text:
                # 滚动到课程名称元素的位置
                driver.execute_script("arguments[0].scrollIntoView();", course_element)
                if task_type!='作业':
                    set_speed(speed, driver)
                # 使用 JavaScript 点击课程名称元素
                driver.execute_script("arguments[0].click();", course_element)
                # 打印选择的课程名称
                print(color.green(f'您已选择《{course_name}》'), flush=True)
                break
        else:
            # 体验最新版本
            driver.execute_script("arguments[0].click();",driver.find_element(By.CSS_SELECTOR, ".experience"))
            print(color.green('正在体验最新版本'), flush=True)
            if not turn_page(driver,'新泛雅'):
                turn_page(driver,'课程')
            element=driver.find_elements(By.XPATH,'//*[@id="stukc"]/div[1]/div[1]/div/a')
            time.sleep(2)
            if len(element)!=0:
                element[0].click()
                driver.find_element(By.XPATH,'//*[experience@id="stukc"]/div[1]/div[1]/div/div/ul/li[1]').click()
            choice_course(driver,course_name,speed,task_type,phone_number)
    except Exception as r:
        #继续教育
        print(color.red(f"未找到《{course_name}》这门课程，请检查名称是否正确，或手动选择你要刷课的课程，打开该课程后等待片刻"),
              flush=True)
        now_window_handles=len(driver.window_handles)
        while len(driver.window_handles)==now_window_handles:
            time.sleep(1)
        time.sleep(1)
        return

def new_find_mission(driver,speed):

    course_list=driver.find_element(By.CLASS_NAME,'list-four')
    #寻找正在学习中的课程
    all_course=course_list.find_elements(By.TAG_NAME,'li')
    for course in all_course:
        try:
            course.find_element(By.CSS_SELECTOR,"[class='list-status studying']").click()
            set_speed(speed, driver)
            return
        except NoSuchElementException:
            pass
    else:
        print(color.red('该页未找到正在学习中的课程，点击下一页'),flush=True)
        driver.find_element(By.CLASS_NAME,'arrow').click()
        time.sleep(2)
        new_find_mission(driver,speed)

def find_mission(driver,task_type,speed,course_name):
    # 点击开始学习
    try:
        element = driver.find_element(By.CSS_SELECTOR,'[class="start-study readclosecoursepop"]')
        element.click()
    except:
        pass
    experience(driver)
    # 点击章节/作业标签
    elements=driver.find_elements(By.CLASS_NAME, 'nav_content')
    if not elements:
       driver.find_element(By.CSS_SELECTOR, "li[data-nav-name='章节']").click()
    for element in elements:
        if element.text== task_type:
            element.click()
            break
    try:
        driver.switch_to.frame(driver.find_element(By.TAG_NAME, 'iframe'))
    except NoSuchElementException:
        table = driver.find_element(By.CSS_SELECTOR, "[class='tabs font15 color333 fl']")
        # 点击全部知识点
        table.find_elements(By.TAG_NAME, 'a')[2].click()
        time.sleep(1)
        new_find_mission(driver,speed)
        return True
    # 切换到名为 frame_content-zj 的 iframe
    if task_type == '作业':
        return True
    try:
        # 查找待完成任务点的元素
        element = driver.find_element(By.CSS_SELECTOR, '.catalog_tishi120')
    except:
        driver.switch_to.default_content()
        iframes=driver.find_elements(By.TAG_NAME, 'iframe')
        print(len(iframes))
        for iframe in iframes:
            driver.switch_to.frame(iframe)
            try:
                element= driver.find_element(By.CSS_SELECTOR, '.catalog_tishi120')
                break
            except:
                driver.switch_to.default_content()
                continue
        else:
            print(color.red('所有任务点均已完成'),flush=True)
            return False
    refresh_process(driver,course_name)
    # 打印提示信息，表示已检测到未完成点
    print(color.magenta('已检测到未完成点'),flush=True)
    time.sleep(0.5)
    #滚动到未完成的任务点的位置
    driver.execute_script("arguments[0].scrollIntoView();", element)
    set_speed(speed, driver)
    # 点击待完成任务点的元素
    driver.execute_script("arguments[0].click();", element)
    return True

def refresh_process(driver,course_name):
    try:
        process_text=driver.find_element(By.CLASS_NAME, 'xs_head_name').text.strip()
        # 分别提取两个数字
        match = re.search(r'已完成任务点:\s*(\d+)/(\d+)', process_text)
        if match:
            done = int(match.group(1))  # 7
            total = int(match.group(2))  # 17
            save_process(course_name,done,total)
    except Exception as r:
        print(color.red(f'刷新进度失败'), flush=True)

def turn_page(driver,page_name):
    time.sleep(1)
    for handle in driver.window_handles:
        # print(len(driver.window_handles))
        # 先切换到该窗口
        driver.switch_to.window(handle)
        # 得到该窗口的标题栏字符串，判断是不是我们要操作的那个窗口
        if page_name in driver.title:
            # print(driver.title)
            # 如果是，那么这时候WebDriver对象就是对应的该该窗口，正好，跳出循环，
            return True
        else:
            continue
    return False

def fold(driver):
    """折叠侧边目录"""
    try:
        element = driver.find_element(By.XPATH, '//*[@id="selector"]/div[2]')
        element.click()
        time.sleep(1)
    except:
        pass

def set_speed(speed, driver):
    driver.execute_script("document.querySelectorAll('video,audio').forEach(v => v.playbackRate = arguments[0]);", float(speed))

def page_message(driver):
    """检测页面内容类型，返回包含视频、PPT、测验、直播、讨论、音频、阅读的字典"""
    # 内容类型配置：(名称, 查找方式, 选择器)
    CONTENT_TYPES = [
        ('视频', By.CSS_SELECTOR, '[class="ans-attach-online ans-insertvideo-online"]'),
        ('ppt', By.CSS_SELECTOR, '[class="ans-attach-online insertdoc-online-ppt"]'),
        ('ppt', By.CSS_SELECTOR, '[class="ans-attach-online insertdoc-online-pdf"]'),
        ('测验', By.XPATH, '//iframe[starts-with(@src,"/ananas/modules/work/index.html")]'),
        ('直播', By.CSS_SELECTOR, '[src^="/ananas/modules/live/index.html"]'),
        ('讨论', By.CSS_SELECTOR, '[src^="/ananas/modules/insertbbs/index.html"]'),
        ('音频', By.CSS_SELECTOR, '[class="ans-attach-online ans-insertaudio"]'),
        ('阅读', By.CSS_SELECTOR, '[class="ans-attach-online ans-book"]'),
        ('阅读', By.CSS_SELECTOR, '[src^="/ananas/modules/read/indexV2.html"]'),
    ]

    driver.switch_to.default_content()
    page_message_dict = {}

    original_wait = driver.timeouts.implicit_wait  # 保存原始等待时间
    driver.implicitly_wait(0)

    try:
        iframe = driver.find_element(By.ID, 'iframe')
        driver.switch_to.frame(iframe)

        for name, by, selector in CONTENT_TYPES:
            if name in page_message_dict:
                continue  # 已找到的类型跳过
            try:
                driver.find_element(by, selector)
                page_message_dict[name] = selector
            except NoSuchElementException:
                pass
    except NoSuchElementException:
        pass
    finally:
        driver.implicitly_wait(original_wait)  # 恢复原始等待时间

    return page_message_dict

def click_next_page(driver, pass_face):
    """点击下一页按钮，处理各种异常情况"""
    global error_num
    NEXT_PAGE_XPATH = '//*[@id="prevNextFocusNext"]'
    try:
        driver.find_element(By.XPATH, NEXT_PAGE_XPATH).click()
        return True
    except ElementNotInteractableException:
        print(color.red('🎉 🎉 该课程全部已完结，撒花！！！'), flush=True)
        return False
    except ElementClickInterceptedException:
    #     print(color.red('点击被拦截，尝试将浏览器最大化,如果还是报错，请在下次打开浏览器后手动把浏览器最大化'), flush=True)
    #     driver.maximize_window()
        time.sleep(1)
        driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, NEXT_PAGE_XPATH))
    except NoSuchElementException:
        print(color.red('加载中...'), flush=True)
        driver.implicitly_wait(5)
        error_num+=1
        if error_num==6:
            raise RuntimeError('无法定位下一页，课程任务未确认完成')
        try:
            driver.find_element(By.XPATH, NEXT_PAGE_XPATH).click()
        except Exception as e:
            driver.refresh()
            print(color.red(f'出错了，刷新一下'), flush=True)
            delete_face_popup(driver,pass_face)
            fold(driver)
        finally:
            driver.implicitly_wait(2)
    return True

chapter_name=''
def check_chapter_active(driver,multi_device):
    """判断该章节是否正在被学习"""
    global chapter_name
    if not multi_device:
        return True
    element = driver.find_element(By.CLASS_NAME, 'prev_title')
    chapter_name = element.get_attribute('title')
    record_path = fr'task\record\studying_record.txt'
    marker = f'正在刷{chapter_name}...\n'
    try:
        with open(record_path, 'r', encoding='utf-8') as f:
            if marker in f.read():
                print(color.yellow(f'检测到{chapter_name}章节正在学习中，跳过'), flush=True)
                return False
    except FileNotFoundError:
        pass
    with open(record_path, 'a', encoding='utf-8') as f:
        f.write(marker)
    return True

def delete_record():
    """删除该章节的正在学习记录"""
    record_path = fr'task\record\studying_record.txt'
    try:
        with open(record_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return
    if chapter_name=='':
        content = re.sub(r'正在刷.*?\.\.\.\n', '', content)
    else:
        content = content.replace(f'正在刷{chapter_name}...\n', '')
    with open(record_path, 'w', encoding='utf-8') as f:
        f.write(content)

def run(driver,choice,course_name,API,lock_screen,pass_face,video_title_choice,
        discussion_choice,after_finish_question,pass_vido,speed,multi_device):
    while True:
        cond=True
        delete_face_popup(driver,pass_face)
        if check_chapter_active(driver,multi_device):
            print(color.green('正在检测页面内容'), flush=True)
            page_message_dict=page_message(driver)
            if len(page_message_dict)==0:
                print(color.red('该页面无法识别'),flush=True)
            else:
                print(color.green(f'该页面含有{list(page_message_dict.keys())}'),flush=True)
                if 'ppt' in page_message_dict.keys():
                    __ppt(driver,course_name)
                if '直播' in page_message_dict.keys():
                    watch_live(driver,page_message_dict['直播'],course_name)
                if '音频' in page_message_dict.keys():
                    play_audio(driver,page_message_dict['音频'],course_name)
                if '讨论' in page_message_dict.keys():
                    if discussion_choice!='跳过讨论':
                        finish_discussion(driver,API,page_message_dict['讨论'],discussion_choice,course_name)
                    else:
                        print(color.yellow(f'您已选择{discussion_choice}'), flush=True)

                if '阅读' in page_message_dict.keys():
                    reading(driver,page_message_dict['阅读'],course_name)
                if '视频' in page_message_dict.keys():
                    try:
                        study_page(driver,course_name,lock_screen,API,video_title_choice,pass_vido,speed,pass_face)
                    except Exception as e:
                        raise RuntimeError('视频任务失败') from e
                if '测验' in page_message_dict.keys():
                    if choice!='不刷题':
                        finish_quiz(driver, course_name, API, choice,after_finish_question)
                    else:
                        print(color.yellow('您已选择不刷题，即将跳过测试题'),flush=True)
            delete_record()
        driver.switch_to.default_content()
        if cond:
            print(color.green('跳转下一页'), flush=True)
            if not click_next_page(driver, pass_face):
                break
            # 确认
            try:
                driver.find_element(By.XPATH, '//*[@id="mainid"]/div[1]/div/div[3]/a[2]').click()
            except:
                pass
        else:
            delete_face_popup(driver,pass_face)
            fold(driver)
        time.sleep(1)

