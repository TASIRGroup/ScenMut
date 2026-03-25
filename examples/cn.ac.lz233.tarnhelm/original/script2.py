# This sample code supports Appium Python client >=2.3.0
# pip install Appium-Python-Client
# Then you can paste this into a file and simply run with Python
from time import sleep

from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy

# For W3C actions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

options = AppiumOptions()
options.load_capabilities({
    "platformName": "Android",
    "appium:automationName": "uiautomator2",
    "appium:deviceName": "android",
    "appium:appPackage": "cn.ac.lz233.tarnhelm",
    "appium:appActivity": "cn.ac.lz233.tarnhelm.ui.main.MainActivity",
    "appium:language": "en",
    "appium:locale": "US",
    "appium:serverUrl": "http://localhost:4723",
    "appium:ensureWebviewsHavePages": True,
    "appium:nativeWebScreenshot": True,
    "appium:newCommandTimeout": 3600,
    "appium:connectHardwareKeyboard": True
})

driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
el6 = driver.find_element(by=AppiumBy.XPATH, value='//androidx.cardview.widget.CardView[@resource-id="cn.ac.lz233.tarnhelm:id/rulesCardView"]/android.widget.RelativeLayout')
el6.click()
el7 = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.LinearLayout[@content-desc="Regexes"]')
el7.click()
el8 = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.Button[@resource-id="cn.ac.lz233.tarnhelm:id/addFab"]')
el8.click()
sleep(1)
el9 = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.EditText[@resource-id="cn.ac.lz233.tarnhelm:id/regexesEditText"]')
el9.send_keys("test")
el10 = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.Button[@resource-id="android:id/button1"]')
el10.click()
el11_text = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.TextView[@resource-id="cn.ac.lz233.tarnhelm:id/regexesContentTextView"]').text
assert el11_text == "test"