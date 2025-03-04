from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import re
import time
import random
import retrying

# 重试装饰器，处理网络错误
@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_page_with_driver(driver, url):
    driver.get(url)
    driver.implicitly_wait(15)
    return driver.page_source

def fetch_detail_page(detail_url, service, chrome_options):
    """
    访问详情页，提取高清图片URL。
    """
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        page_source = fetch_page_with_driver(driver, detail_url)
        detail_soup = BeautifulSoup(page_source, 'html.parser')

        download_button = detail_soup.find('a', class_='wallpaper__download')
        if download_button and download_button.get('href'):
            actual_url = urljoin(detail_url, download_button['href'])
            print(f"从下载按钮找到实际图片链接: {actual_url}")
            driver.quit()
            return actual_url
        else:
            print(f"详情页 {detail_url} 未找到下载按钮或链接")
            driver.quit()
            return None
    except Exception as e:
        print(f"访问详情页 {detail_url} 失败: {str(e)}")
        driver.quit()
        return None
    finally:
        # 随机延迟，模拟人类行为
        time.sleep(random.uniform(1, 3))

def fetch_image_links(url, max_workers=5):
    """
    使用Selenium模拟用户请求，提取所有页面的图片下载链接。
    使用多线程并行访问详情页。
    返回：图片链接列表。
    """
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36")

        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        image_urls = set()
        current_url = url
        page_num = 1

        while current_url:
            print(f"正在爬取第 {page_num} 页: {current_url}")
            page_source = fetch_page_with_driver(driver, current_url)
            soup = BeautifulSoup(page_source, 'html.parser')

            # 提取当前页面的图片详情页链接
            detail_urls = set()
            for img in soup.find_all('img'):
                img_url = img.get('data-src') or img.get('src')
                if img_url:
                    img_url = urljoin(current_url, img_url)
                    if 'wallspic.com' in img_url and 'previews' in img_url:
                        parent_a = img.find_parent('a')
                        if parent_a and parent_a.get('href'):
                            detail_url = urljoin(current_url, parent_a['href'])
                            detail_urls.add(detail_url)

            # 使用多线程并行访问详情页
            print(f"找到 {len(detail_urls)} 个详情页链接，启动多线程爬取...")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(fetch_detail_page, detail_url, service, chrome_options) for detail_url in detail_urls]
                for future in futures:
                    actual_url = future.result()
                    if actual_url:
                        image_urls.add(actual_url)

            # 查找“下一页”链接
            next_page = soup.find('a', attrs={'rel': 'next'}) or soup.find('a', text=re.compile('下一页|Next'))
            if next_page and next_page.get('href'):
                current_url = urljoin(current_url, next_page['href'])
                page_num += 1
            else:
                current_url = None

            # 随机延迟，模拟人类行为
            time.sleep(random.uniform(2, 5))

        driver.quit()
        return list(image_urls)

    except Exception as e:
        print(f"获取图片链接失败: {str(e)}")
        return []

if __name__ == "__main__":
    url = "https://wallspic.com/cn/album/riben_dongman"
    links = fetch_image_links(url, max_workers=5)
    print("所有图片链接:", links)