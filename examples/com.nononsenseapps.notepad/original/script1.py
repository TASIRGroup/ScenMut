# This sample code supports Appium Python client >=2.3.0
# pip install Appium-Python-Client
# Then you can paste this into a file and simply run with Python

from appium import webdriver
from appium.options.common.base import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy

# For W3C actions
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.actions import interaction
from selenium.webdriver.common.actions.action_builder import ActionBuilder
from selenium.webdriver.common.actions.pointer_input import PointerInput

from time import sleep

options = AppiumOptions()
options.load_capabilities({
    "platformName": "Android",
    "appium:automationName": "uiautomator2",
    "appium:deviceName": "android",
    "appium:appPackage": "com.nononsenseapps.notepad.debug",
    "appium:appActivity": "com.nononsenseapps.notepad.activities.main.ActivityMain_",
    "appium:language": "en",
    "appium:locale": "US",
    "appium:serverUrl": "http://localhost:4723",
    "appium:ensureWebviewsHavePages": True,
    "appium:nativeWebScreenshot": True,
    "appium:newCommandTimeout": 3600,
    "appium:connectHardwareKeyboard": True
})

driver = webdriver.Remote("http://127.0.0.1:4723", options=options)

el2 = driver.find_element(AppiumBy.XPATH, '//android.widget.Button[@content-desc="Save and add note"]')
el2.click()
sleep(1)
driver.back()
el3 = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageButton[@content-desc="Remove due date"]')
el3.click()
el4 = driver.find_element(AppiumBy.XPATH, '//android.widget.EditText[@resource-id="com.nononsenseapps.notepad.debug:id/taskText"]')
el4.send_keys("123")
el5 = driver.find_element(AppiumBy.XPATH, '//android.widget.Button[@content-desc="Save and add note"]')
el5.click()
el6 = driver.find_element(AppiumBy.XPATH, '//android.widget.ImageButton[@content-desc="Navigate up"]')
el6.click()
