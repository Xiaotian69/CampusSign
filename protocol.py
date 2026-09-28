"""学习通平台协议常量。

本模块只承载「为实现签到功能而客观必需」的平台协议信息：接口地址、
请求字段名与移动端 User-Agent 等。这些属于接口/协议层面的必要事实，
不构成可版权的代码表达；CxSign 的其余代码（业务流程、匹配逻辑、结果
判定、界面与配置体系）均在此基础上独立实现。
"""

# ===== 接口地址 =====
LOGIN_URL = 'https://passport2.chaoxing.com/api/login'
COURSE_LIST_URL = 'https://mooc1-2.chaoxing.com/visit/courselistdata'
ACTIVITY_LIST_URL = 'https://mobilelearn.chaoxing.com/v2/apis/active/student/activelist'
PRESIGN_URL = 'https://mobilelearn.chaoxing.com/widget/sign/pcStuSignController/preSign'
ADDRESS_URL = 'https://mobilelearn.chaoxing.com/newsign/preSign'
SIGN_URL = 'https://mobilelearn.chaoxing.com/pptSign/stuSignajax'

# ===== 移动端请求头（学习通客户端标识，签到接口所需） =====
MOBILE_HEADERS = {
    'Accept-Encoding': 'gzip, deflate',
    'Accept-Language': 'zh_CN',
    'X-Requested-With': 'com.chaoxing.mobile',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 12; 21121210C Build/SKQ1.211006.001; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/108.0.5359.128 Mobile Safari/537.36 Language/zh_CN com.chaoxing.mobile/ChaoXingStudy_3_6.0.8_android_phone_902_99 (@Kalimdor)',
}

# ===== 位置签到提交字段（平台协议要求的固定值） =====
SIGN_CLIENT_IP = '0.0.0.0'
SIGN_ADDRESS = '中国'
SIGN_APP_TYPE = '15'
SIGN_SUBMIT = '1'

# 位置签到活动在活动列表中对应的类型标识
LOCATION_ACTIVITY_OTHER_ID = '4'
