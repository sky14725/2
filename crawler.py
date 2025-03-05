# crawler.py
import queue
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time
import random
import retrying
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
def create_driver(headless: bool = True) -> webdriver.Chrome:
    """
    创建一个新的 WebDriver 实例。

    Args:
        headless (bool): 是否使用无头模式，默认 True。

    Returns:
        webdriver.Chrome: WebDriver 实例。
    """
    try:
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")

        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("WebDriver 实例创建成功")
        return driver
    except Exception as e:
        print(f"WebDriver 实例创建失败: {str(e)}")
        raise

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_page(url: str, scroll_to_bottom: bool = True, max_pages: int = 5) -> str:
    """
    使用 WebDriver 加载页面，支持下滑自动加载，并在到达底部时点击“下一页”。

    Args:
        url (str): 要加载的页面 URL。
        scroll_to_bottom (bool): 是否下滑加载，默认 True。
        max_pages (int): 最大翻页次数，默认 5。

    Returns:
        str: 页面源代码。
    """
    driver = create_driver(headless=True)
    try:
        print(f"加载页面: {url}")
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        page_source = ""
        page_count = 0

        if scroll_to_bottom:
            last_height = driver.execute_script("return document.documentElement.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                time.sleep(random.uniform(2, 4))
                new_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_height == last_height:
                    print("页面已加载到底部，检查是否可以点击“下一页”")
                    try:
                        next_button = WebDriverWait(driver, 5).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[@rel='next' or contains(text(), '下一页') or contains(text(), 'Next')]"))
                        )
                        if next_button and page_count < max_pages:
                            next_button.click()
                            time.sleep(random.uniform(2, 4))
                            page_count += 1
                            continue
                        else:
                            print(f"未找到“下一页”按钮或已达到最大翻页次数 ({max_pages})，停止翻页")
                            break
                    except Exception as e:
                        print(f"未找到“下一页”按钮或无法点击: {str(e)}")
                        break
                last_height = new_height

        page_source = driver.page_source
        return page_source
    except Exception as e:
        print(f"加载页面 {url} 失败: {str(e)}")
        raise
    finally:
        driver.quit()

def crawl_images(url: str, detail_queue: queue.Queue, max_pages: int = 5) -> None:
    """
    爬取页面，提取图片详情页链接，并将链接放入队列。

    Args:
        url (str): 网页 URL。
        detail_queue (queue.Queue): 存放详情页链接的队列。
        max_pages (int): 最大翻页次数，默认 5。
    """
    try:
        page_num = 1
        while page_num <= max_pages:
            print(f"正在爬取第 {page_num} 页: {url}")
            page_source = fetch_page(url, scroll_to_bottom=True, max_pages=max_pages)
            soup = BeautifulSoup(page_source, 'html.parser')

            # 提取当前页面的图片详情页链接
            detail_urls = set()
            for img in soup.find_all('img'):
                img_url = img.get('data-src') or img.get('src') or img.get('data-original') or img.get('data-lazy-src') or img.get('data-lazy-load') or img.get('data-img') or img.get('srcset') or img.get('data-image')
                if img_url:
                    img_url = urljoin(url, img_url.split(',')[-1].strip().split(' ')[0]) if 'srcset' in img.attrs else img_url
                    print(f"找到图片链接: {img_url}")
                    if 'wallspic.com' in img_url and 'previews' in img_url:
                        parent_a = img.find_parent('a')
                        if parent_a and parent_a.get('href'):
                            detail_url = urljoin(url, parent_a['href'])
                            detail_urls.add(detail_url)
                            print(f"提取详情页链接: {detail_url}")

            if not detail_urls:
                print("未找到任何详情页链接，可能是页面加载失败或结构变化")
                break

            # 将详情页链接放入队列
            for detail_url in detail_urls:
                detail_queue.put(detail_url)

            # 检查是否已到达最后一页
            soup = BeautifulSoup(page_source, 'html.parser')
            next_page = soup.find('a', attrs={'rel': 'next'}) or soup.find('a', string=re.compile('下一页|Next'))
            if not next_page:
                print("未找到下一页链接，结束翻页")
                break

            page_num += 1
            time.sleep(random.uniform(2, 5))

    except Exception as e:
        print(f"爬取图片链接失败: {str(e)}")
    finally:
        # 放入一个标记，表示爬取结束
        detail_queue.put(None)