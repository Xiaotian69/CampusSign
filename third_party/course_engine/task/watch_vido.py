# Copyright (c) 2025 Mortal004
# All rights reserved.
# This software is provided for non-commercial use only.
# For more information, see the LICENSE file in the root directory of this project.
import json
import random
from selenium.common import  NoAlertPresentException
import time
import ast

from selenium.webdriver.common.action_chains import ActionChains

from third_party.course_engine.task.tool.DeepSeekAsk import DeepSeekAsk
from third_party.course_engine.task.tool import color
from selenium.webdriver.common.by import By
import itertools

from third_party.course_engine.task.tool.common import save_record
from third_party.course_engine.task.tool.face import delete_face_popup

drag_progress_condition = True


def click_video_progress_end(driver, pass_vido):
    return

def generate_combinations_list(input_list):
    """
    返回列表形式的组合，完整组合放在第一位
    """
    n = len(input_list)

    if n == 3:
        # 三者都出现的情况（放在第一位）
        triple = [input_list.copy()]
        # 两两组合的所有可能
        pairs = [list(combo) for combo in itertools.combinations(input_list, 2)]
        return triple + pairs

    elif n == 4:
        # 取四个元素的情况（放在第一位）
        quadruple = [input_list.copy()]
        # 取三个元素的所有可能
        pairs = [list(combo) for combo in itertools.combinations(input_list, 2)]
        triples = [list(combo) for combo in itertools.combinations(input_list, 3)]
        return quadruple + triples + pairs
    else:
        return [input_list]

def check_internet(driver):
    try:
        internet_choice=driver.find_element(By.CSS_SELECTOR,"[class='ans-vjserrdisplay-opts']")
        # print(color.red('网络异常'), flush=True)
        choice_list=internet_choice.find_elements(By.CSS_SELECTOR,"[name='ans-vjserrdisplay-opt']")
        for choice in choice_list:
            choice.click()
    except:
        pass

def get_answer(API,question,typ):
    answer = []
    try:
        answer = DeepSeekAsk(API, question, typ)
    except Exception as e:
        print(f'答题时出错了{e}',flush=True)
    return answer

def finish_video_question(options_txt,options,answer,question_type):
    answer_num = []
    option_num = 0
    if question_type == '单选题' or question_type == '判断题':
        for option in options_txt:
            if answer[0] in option:
                break
            option_num += 1
        answer_num.append(option_num)
    elif question_type == '多选题':
        if len(answer) == 1:
            lst = answer[0]
        else:
            lst = answer
        for option in options_txt:
            for ans in lst:
                if ans in option:
                    answer_num.append(option_num)
            option_num += 1
        answer_num = list(set(answer_num))
    # 点击正确答案
    for ans in answer_num:
        checked=options[ans].find_elements(By.CSS_SELECTOR,'[checked="checked"]')
        if not checked:
            options[ans].click()
            time.sleep(1)
        else:
            print(color.yellow(f'已选择选项{ans}'), flush=True)
            continue

def check_video_question(driver,API,video_title_choice):
    try:
        element=driver.find_element(By.CLASS_NAME,'tkTopic')
        print(color.yellow('已检测到视频中有题目'), flush=True)
        if video_title_choice not in ('DeepSeek AI', '随机答题'):
            print('请手动完成视频题目。', flush=True)
            return
        question_title = element.find_element(By.CLASS_NAME, 'tkItem_title').text
        try:
            question_type=element.find_element(By.CLASS_NAME,'tkTopic_type').text
        except:
            question_type=element.find_element(By.CLASS_NAME,'tkTopic_title').text
        options = element.find_element(By.CLASS_NAME, 'tkItem_ul')
        options = options.find_elements(By.TAG_NAME, 'li')
        options_txt=[option.text for option in options]
        submit = element.find_element(By.ID, 'videoquiz-submit')
        if video_title_choice=='DeepSeek AI':
            answer = get_answer(API,question_title+'\n'+str(options_txt),question_type)
            if type(answer) is str:
                try:
                    answer = ast.literal_eval(answer)  # 转换为列表
                except:
                    answer = [answer]
            if not answer:
                print(color.red(f'答题失败,无答案'), flush=True)
                return
            else:
                finish_video_question(options_txt,options,answer,question_type)
                submit.click()
        if video_title_choice == '随机答题':
            random.choice(options).click()
            submit.click()
        #继续学习
        try:
            continue_learn=element.find_element(By.ID,'videoquiz-continue')
            continue_learn.click()
        except :
            pass
        try:
            return_video=driver.find_element(By.CSS_SELECTOR, '[class="bntWhiteBorder ans-videoquiz-back fr"]')
            return_video.click()
        except:
            pass
    except:
        return

VIDEO_PROBE_JS = """
var v = document.querySelector('video');
if (!v) { return null; }
return {
  paused: v.paused,
  t: v.currentTime,
  d: (isFinite(v.duration) ? v.duration : 0),
  ended: v.ended,
  rs: v.readyState,
  err: (v.error ? v.error.code : 0)
};
"""

_stall_limit_seconds = 30      # 连续无法推进多少秒才判失败（原来 3 秒）
_reload_every_seconds = 15     # 每卡这么久尝试原地重载播放器
_speed_noted = set()


def video_probe(driver):
    """读取播放器真实状态；读不到返回 None。界面文本不再作为判据。"""
    try:
        return driver.execute_script(VIDEO_PROBE_JS)
    except Exception:
        return None


def video_duration_text(driver):
    """从 video 元素取总时长，格式 m:ss；取不到返回 None。"""
    try:
        seconds = driver.execute_script(
            "var v = document.querySelector('video'); if (!v) { return 0; }"
            "return (isFinite(v.duration) ? v.duration : 0);")
    except Exception:
        return None
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return None
    if not seconds or seconds <= 0:
        return None
    total = int(round(seconds))
    return '%d:%02d' % (total // 60, total % 60)


def apply_speed(driver, speed):
    """设置倍速并读回真实值；平台限制时只提示一次，不反复刷屏。"""
    try:
        actual = driver.execute_script(
            "var v = document.querySelector('video'); if (!v) { return 0; }"
            "try { v.playbackRate = arguments[0]; } catch (e) {}"
            "return v.playbackRate;", float(speed))
    except Exception:
        return None
    try:
        actual = float(actual)
    except (TypeError, ValueError):
        return None
    if 0 < actual and abs(actual - float(speed)) > 0.05 and actual not in _speed_noted:
        _speed_noted.add(actual)
        print(color.yellow(f'平台把倍速限制为 {actual} 倍，按实际速率播放'), flush=True)
    return actual


def resume_video(driver):
    """三级恢复：JS play() -> 播放按钮（宽松匹配）-> 放弃。"""
    try:
        played = driver.execute_script(
            "var v = document.querySelector('video'); if (!v) { return false; }"
            "var p = v.play(); if (p && p.catch) { p.catch(function () {}); }"
            "return true;")
        if played:
            return True
    except Exception:
        pass
    for selector in ('button.vjs-play-control', '[class*="vjs-play-control"]', '.vjs-big-play-button'):
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            classes = element.get_attribute('class') or ''
            if selector == '.vjs-big-play-button' or 'vjs-paused' in classes:
                element.click()
                return True
        except Exception:
            continue
    return False


def check_vido_play(driver, last_time, current_time,speed,pass_face,vido_iframe):
    """保留旧签名以兼容外部调用；实际判停已改到 check_vido_finish 里用 video_probe。"""
    if last_time == current_time:
        return resume_video(driver)
    return True

def handle_video_error_alert(driver):
    try:
        alert = driver.switch_to.alert
        alert_text = alert.text
        if "视频播放异常" in alert_text:
            print(color.red("检测到视频播放异常弹窗，尝试刷新页面..."))
            alert.accept()
            time.sleep(2)
            driver.refresh()
            # 刷新后需要重新进入 iframe，具体逻辑根据实际情况补充
            raise Exception('视频播放异常')
        else:
            alert.accept()
            raise Exception('视频播放异常')
    except NoAlertPresentException:
        return

def check_vido_finish(driver,i,time_start,total_time,vido_iframe,lock_screen,API,video_title_choice,speed,pass_face):
    """等待任务点完成。

    判据从「界面时间文本」换成 video 元素的真实状态：
      - 暂停时先尝试 JS play()，再退回按钮点击；
      - 连续无法推进 30 秒才判失败（原来 3 秒）；
      - 中途每 15 秒原地重载一次播放器，处理断流与线路菜单；
      - 播放结束但任务点未完成时，用 JS 重播一次。
    """
    stall_seconds = 0
    last_position = None
    replayed = False

    while True:
        time.sleep(1)

        # 1) 任务点是否已完成
        driver.switch_to.default_content()
        driver.switch_to.frame('iframe')
        try:
            elements2 = driver.find_elements(By.CLASS_NAME, 'ans-job-icon-clear ')
            element2 = elements2[i]
            parent_element2 = element2.find_element(By.XPATH, "..")
            parent_class = parent_element2.get_attribute("class") or ''
            txt = element2.get_attribute('aria-label')
        except Exception:
            txt, parent_class = '', ''
        if txt == '任务点已完成' or 'ans-attach-ct ans-job-finished' in parent_class:
            print(color.green(f'已完成第{i + 1}个视频'), flush=True)
            print(color.green('总共耗费了%.2f秒.' % (time.time() - time_start)), flush=True)
            break

        # 2) 进播放器读真实状态
        driver.switch_to.default_content()
        driver.switch_to.frame('iframe')
        driver.switch_to.frame(vido_iframe)
        info = video_probe(driver)

        if info is None:
            stall_seconds += 1
        else:
            position, duration = info.get('t', 0), info.get('d', 0)
            if duration > 0:
                apply_speed(driver, speed)
            check_internet(driver)
            check_video_question(driver, API, video_title_choice)

            if info.get('ended') or (duration > 0 and position >= duration - 1):
                if replayed:
                    raise RuntimeError('视频播放结束但平台未确认任务点完成')
                replayed = True
                print(color.yellow('视频已播放完毕，任务点未完成，重播一次'), flush=True)
                driver.execute_script(
                    "var v = document.querySelector('video');"
                    "if (v) { v.currentTime = 0; v.play(); }")
                time.sleep(2)
                continue

            if info.get('paused'):
                stall_seconds += 1
                print(color.red(f'视频暂停中，第 {stall_seconds} 秒尝试恢复'), flush=True)
                if not resume_video(driver):
                    driver.switch_to.default_content()
                    delete_face_popup(driver, pass_face)
                    driver.switch_to.frame('iframe')
                    driver.switch_to.frame(vido_iframe)
            elif last_position is not None and abs(position - last_position) < 0.6:
                stall_seconds += 1
                print(color.yellow(f'播放无进展，第 {stall_seconds} 秒'), flush=True)
            else:
                stall_seconds = 0
            last_position = position

        # 3) 每卡 15 秒原地重载一次播放器
        if 0 < stall_seconds < _stall_limit_seconds and stall_seconds % _reload_every_seconds == 0:
            print(color.yellow('尝试原地重载播放器'), flush=True)
            try:
                driver.execute_script(
                    "var f = document.querySelector('iframe'); if (f) { f.src = f.src; }")
                time.sleep(3)
            except Exception:
                pass

        if stall_seconds >= _stall_limit_seconds:
            raise RuntimeError(f'视频连续 {stall_seconds} 秒无法恢复播放')

        if lock_screen:
            import ctypes
            import os
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
    return True

def study_page(driver,course_name,lock_screen,API,video_title_choice,pass_vido,speed,pass_face):
    global drag_progress_condition
    driver.switch_to.default_content()
    driver.switch_to.frame('iframe')
    try:
        # 判断是否完成任务
        elements1 = driver.find_elements(By.CLASS_NAME, 'ans-job-icon-clear ')
        print(color.magenta(f'已检测到{len(elements1)}个视频包含有任务点'),flush=True)
    except:
        driver.execute_script("window.scrollBy(0, 250)")
        print(color.green('视频已完成,点击下一节'),flush=True)
        return

    for i in range(len(elements1)):
        drag_progress_condition = True
        element1=elements1[i]
        # 定位到该元素的上一级（父元素）
        parent_element = element1.find_element(By.XPATH, "..")
        try:
            # 获取 parent_element 的class值
            parent_element_class=parent_element.get_attribute("class")
            txt = element1.get_attribute('aria-label')
        except:
            txt = ''
            parent_element_class=''
        if txt == '任务点未完成' and 'ans-attach-ct' in parent_element_class:
            vido_iframe=element1.find_element(By.XPATH, "following-sibling::iframe[1]")
            driver.execute_script("arguments[0].scrollIntoView();", vido_iframe)
            driver.switch_to.frame(vido_iframe)
            print(color.green(f'开始播放第{i + 1}个视频'),flush=True)
            time_start=time.time()
            try:
                driver.find_element(By.CLASS_NAME,'vjs-big-play-button').click()
            except:
                pass
            #点击我知道了
            driver.switch_to.default_content()
            delete_face_popup(driver,pass_face)
            driver.switch_to.frame('iframe')
            driver.switch_to.frame(vido_iframe)

            try:
                element=driver.find_element(By.CLASS_NAME,'writeNote_vid_blue')
                element.click()
            except:
                pass
            try:
                print(color.blue('调节音量'), flush=True)
                element = driver.find_element(By.XPATH, '//*[@id="video"]/div[6]/div[6]')
                element.click()
                print(color.green('调节成功'), flush=True)
            except:
                print(color.yellow('未找到音量，或已经调节'), flush=True)

            time.sleep(1)
            try:
                total_time = (driver.find_element(By.CLASS_NAME, 'vjs-duration-display').text or '').strip()
            except Exception:
                total_time = ''
            if total_time in ('', '0:00', '0:00:00'):
                total_time = video_duration_text(driver)
                if total_time:
                    print(color.yellow(f'界面上取不到时长，从播放器读出：{total_time}'), flush=True)
                else:
                    print(color.red('获取视频总时长失败'), flush=True)
                    total_time = '1'
            else:
                print(color.green(f'该视频总时长为：{total_time}'),flush=True)
            click_video_progress_end(driver,pass_vido)
            print(color.yellow('请不要将窗口最小化，这有可能导致脚本异常\n视频播放完毕会自动跳转\n正在观看视频中……'),flush=True)
            driver.switch_to.default_content()
            driver.switch_to.frame('iframe')
            apply_speed(driver, speed)
            check_vido_finish(driver,i,time_start,total_time,vido_iframe,lock_screen,API,video_title_choice,speed,pass_face)
            save_record(driver, course_name, time, vido_iframe, '视频')
        driver.switch_to.default_content()
        # check_face(driver,driver.current_url,'popDiv1 wid640  faceCollectQrPopVideo  popClass faceRecognition_0')
        driver.switch_to.frame('iframe')
    print(color.green('所有视频均已完成'),flush=True)
    return
