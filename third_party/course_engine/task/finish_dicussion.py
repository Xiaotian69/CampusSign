import random

from selenium.webdriver.common.by import By
import ast

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from third_party.course_engine.task.tool.DeepSeekAsk import DeepSeekAsk
import time
from third_party.course_engine.task.tool.common import Common,turn_page

class Discussion(Common):
    def __init__(self,driver,API,iframe_element,discussion_choice,course_name):
        super().__init__(driver,iframe_element,"讨论",course_name)
        self.question = None
        self.answer = []
        self.API=API
        self.discussion_choice=discussion_choice
    def get_answer(self):
        if self.discussion_choice == 'DeepSeek AI':
            self.answer = DeepSeekAsk(self.API, self.question, '简答题')

    def start(self):
        # 方式一：等待可点击
        iframe = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable(self.iframe)
        )
        iframe.click()

        turn_page(self.driver,'话题详情')
        self.question=self.driver.find_element(By.CLASS_NAME,'topicDetail_title').text
        print(f'当前话题为{self.question}',flush=True)
        #回复的窗口元素
        replay_element=self.driver.find_element(By.CLASS_NAME,'textareawrap')
        replay_element=replay_element.find_element(By.TAG_NAME,'textarea')
        replay_button=self.driver.find_element(By.CSS_SELECTOR,'[class="jb_btn jb_btn_92 fr fs14 addReply"]')
        try:
            self.get_answer()
        except Exception as e:
            print(f'答题时出错了,{e}\n即将跳过该任务', flush=True)
        # self.answer = '你好'
        if type(self.answer) is str:
            try:
                self.answer = ast.literal_eval(self.answer)  # 转换为列表
            except:
                self.answer = [self.answer]
        if self.answer:
            replay_element.click()
            replay_element.send_keys(self.answer[0])
            print(f'已输入{self.answer[0]},3秒后点击提交',flush=True)
            time.sleep(3)
            replay_button.click()
        time.sleep(1)
        self.driver.close()
        turn_page(self.driver,'学生学习页面')
def finish_discussion(driver,API,iframe_element,discussion_choice,course_name):
    discussion= Discussion(driver,API,iframe_element,discussion_choice,course_name)
    discussion.main()
