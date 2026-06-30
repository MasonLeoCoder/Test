from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("https://www.baidu.com")

    page.wait_for_timeout(5000)

    page.fill("#chat-textarea","测试")

    page.wait_for_timeout(2000)

    page.get_by_role("button",name="百度一下").click()

    page.wait_for_timeout(500000)


    browser.close()