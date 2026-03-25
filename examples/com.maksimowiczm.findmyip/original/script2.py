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
	"appium:appPackage": "com.maksimowiczm.findmyip",
	"appium:appActivity": "com.maksimowiczm.findmyip.infrastructure.android.MainActivity",
	"appium:language": "en",
	"appium:locale": "US",
	"appium:serverUrl": "http://localhost:4723",
	"appium:ensureWebviewsHavePages": True,
	"appium:nativeWebScreenshot": True,
	"appium:newCommandTimeout": 3600,
	"appium:connectHardwareKeyboard": True
})

driver = webdriver.Remote("http://127.0.0.1:4723", options=options)

el1 = driver.find_element(by=AppiumBy.XPATH, value='//android.widget.Button')
el1.click()
sleep(1)
el2 = driver.find_element(by=AppiumBy.XPATH, value='//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.widget.Button')
el2.click()
sleep(1)
el3 = driver.find_element(by=AppiumBy.XPATH, value='//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View/android.view.View[2]/android.widget.Button')
el3.click()
sleep(1)
el4 = driver.find_element(by=AppiumBy.XPATH, value='//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[2]/android.view.View/android.view.View[3]/android.view.View[2]')
el4.click()
sleep(1)
el5 = driver.find_element(by=AppiumBy.XPATH, value='//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View[5]')
el5.click()
sleep(1)
is_displayed = driver.find_element(by=AppiumBy.XPATH, value='//androidx.compose.ui.platform.ComposeView/android.view.View/android.view.View/android.view.View[1]/android.view.View[1]/android.view.View[1]').is_displayed()
assert is_displayed == True