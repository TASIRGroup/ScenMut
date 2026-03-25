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
    "appium:appPackage": "com.bobek.compass",
    "appium:appActivity": "com.bobek.compass.MainActivity",
    "appium:language": "en",
    "appium:locale": "US",
    "appium:serverUrl": "http://localhost:4723",
    "appium:ensureWebviewsHavePages": True,
    "appium:nativeWebScreenshot": True,
    "appium:newCommandTimeout": 3600,
    "appium:connectHardwareKeyboard": True
})

driver = webdriver.Remote("http://127.0.0.1:4723", options=options)

el1 = driver.find_element(AppiumBy.XPATH, '//android.widget.Button[@content-desc="Settings"]')
el1.click()
sleep(1)
el2 = driver.find_element(AppiumBy.XPATH, '//androidx.recyclerview.widget.RecyclerView[@resource-id="com.bobek.compass:id/recycler_view"]/android.widget.LinearLayout[5]/android.widget.RelativeLayout')
el2.click()
sleep(1)
el3 = driver.find_element(AppiumBy.XPATH, '//android.widget.CheckedTextView[@resource-id="android:id/text1" and @text="Light"]')
el3.click()
