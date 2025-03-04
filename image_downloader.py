import os
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor
import threading
import re
import time
import random
import retrying
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from typing import List, Optional, Dict

# 保存路径锁，确保文件写入安全
file_lock = threading.Lock()

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
            chrome_options.add_argument("--headless=new")  # 使用新的 headless 模式
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
def fetch_page_with_driver(url: str, scroll_to_bottom: bool = True, max_pages: int = 5) -> str:
    """
    使用 WebDriver 加载页面，支持下滑自动加载，并在到达底部时点击“下一页”。

    Args:
        url (str): 要加载的页面 URL。
        scroll_to_bottom (bool): 是否下滑加载，默认 True。
        max_pages (int): 最大翻页次数，默认 5。

    Returns:
        str: 页面源代码。
    """
    driver = create_driver()
    try:
        print(f"加载页面: {url}")
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

        page_source = ""
        page_count = 0

        if scroll_to_bottom:
            # 模拟下滑加载
            last_height = driver.execute_script("return document.documentElement.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
                time.sleep(random.uniform(2, 4))  # 等待加载
                new_height = driver.execute_script("return document.documentElement.scrollHeight")
                if new_height == last_height:
                    print("页面已加载到底部，检查是否可以点击“下一页”")
                    # 尝试点击“下一页”按钮
                    try:
                        next_button = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable((By.XPATH, "//a[@rel='next' or contains(text(), '下一页') or contains(text(), 'Next')]"))
                        )
                        if next_button and page_count < max_pages:
                            next_button.click()
                            time.sleep(random.uniform(2, 4))  # 等待页面加载
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

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
def download_image(url: str, save_dir: str, headers: Dict[str, str] = {'User-Agent': 'Mozilla/5.0'}) -> bool:
    """
    下载单个图片，使用线程锁确保文件写入安全。

    Args:
        url (str): 图片 URL。
        save_dir (str): 保存目录。
        headers (Dict[str, str]): HTTP 请求头，默认包含 User-Agent。

    Returns:
        bool: 是否下载成功。
    """
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        response.raise_for_status()
        file_name = url.split('/')[-1].split('?')[0] or f"image_{hash(url)}.jpg"
        file_path = os.path.join(save_dir, file_name)

        with file_lock:
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        print(f"已下载图片: {file_path}")
        return True
    except Exception as e:
        print(f"下载 {url} 失败: {str(e)}")
        return False
    finally:
        time.sleep(random.uniform(0.5, 2))

@retrying.retry(stop_max_attempt_number=3, wait_fixed=2000)
def fetch_detail_page(detail_url: str) -> Optional[str]:
    """
    访问详情页，提取高清图片URL。

    Args:
        detail_url (str): 详情页 URL。

    Returns:
        Optional[str]: 高清图片 URL，如果未找到则返回 None。
    """
    driver = create_driver()
    try:
        page_source = fetch_page_with_driver(detail_url, scroll_to_bottom=False)
        detail_soup = BeautifulSoup(page_source, 'html.parser')

        download_button = detail_soup.find('a', class_='wallpaper__download')
        if download_button and download_button.get('href'):
            actual_url = urljoin(detail_url, download_button['href'])
            print(f"从下载按钮找到实际图片链接: {actual_url}")
            return actual_url
        else:
            print(f"详情页 {detail_url} 未找到下载按钮或链接")
            return None
    except Exception as e:
        print(f"访问详情页 {detail_url} 失败: {str(e)}")
        return None
    finally:
        driver.quit()
        time.sleep(random.uniform(1, 3))

def fetch_image_links(url: str, max_workers: int = 5, headless: bool = True, max_pages: int = 5) -> List[str]:
    """
    使用Selenium模拟用户请求，提取所有页面的图片下载链接。
    使用多线程并行访问详情页。

    Args:
        url (str): 网页 URL。
        max_workers (int): 最大线程数，默认 5。
        headless (bool): 是否使用无头模式，默认 True。
        max_pages (int): 最大翻页次数，默认 2。

    Returns:
        List[str]: 高清图片 URL 列表。
    """
    image_urls = set()
    page_num = 1

    try:
        while page_num <= max_pages:
            print(f"正在爬取第 {page_num} 页: {url}")
            page_source = fetch_page_with_driver(url, scroll_to_bottom=True, max_pages=max_pages)
            soup = BeautifulSoup(page_source, 'html.parser')

            # 提取当前页面的图片详情页链接
            detail_urls = set()
            for img in soup.find_all('img'):
                img_url = img.get('data-src') or img.get('src') or img.get('data-original') or img.get('data-lazy-src') or img.get('data-lazy-load') or img.get('data-img') or img.get('srcset')
                if img_url:
                    img_url = urljoin(url, img_url.split(',')[-1].strip().split(' ')[0]) if 'srcset' in img.attrs else img_url  # 处理 srcset
                    print(f"找到图片链接: {img_url}")
                    if 'wallspic.com' in img_url and 'previews' in img_url:
                        parent_a = img.find_parent('a')
                        if parent_a and parent_a.get('href'):
                            detail_url = urljoin(url, parent_a['href'])
                            detail_urls.add(detail_url)
                            print(f"提取详情页链接: {detail_url}")

            if not detail_urls:
                print("未找到任何详情页链接，可能是页面加载失败或结构变化")
                break  # 如果当前页面没有找到详情页链接，停止继续翻页

            # 使用多线程并行访问详情页
            print(f"找到 {len(detail_urls)} 个详情页链接，启动多线程爬取...")
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(fetch_detail_page, detail_url) for detail_url in detail_urls]
                for future in futures:
                    actual_url = future.result()
                    if actual_url:
                        image_urls.add(actual_url)

            # 检查是否已到达最后一页（fetch_page_with_driver 已处理“下一页”点击）
            soup = BeautifulSoup(page_source, 'html.parser')
            next_page = soup.find('a', attrs={'rel': 'next'}) or soup.find('a', string=re.compile('下一页|Next'))
            if not next_page:
                print("未找到下一页链接，结束翻页")
                break

            page_num += 1
            time.sleep(random.uniform(2, 5))

        return list(image_urls)

    except Exception as e:
        print(f"获取图片链接失败: {str(e)}")
        return []

def main():
    print("欢迎使用简易网页图片下载器（基于EasySpider的图片处理逻辑）")
    url = input("请输入要下载图片的网页URL（例如 https://example.com）：").strip()
    save_dir = input("请输入保存图片的目录（直接回车默认为 'images'）：").strip() or "images"
    max_workers = int(input("请输入最大线程数（默认 5）：").strip() or 5)
    max_pages = int(input("请输入最大翻页次数（默认 5）：").strip() or 5)
    headless = input("是否使用无头模式（默认是，输入 'n' 关闭）：").strip().lower() != 'n'

    if not url.startswith('http://') and not url.startswith('https://'):
        print("错误：URL必须以 http:// 或 https:// 开头")
        return

    # 爬取图片链接
    image_urls = fetch_image_links(url, max_workers=max_workers, headless=headless, max_pages=max_pages)
    if not image_urls:
        print("未找到任何图片链接！")
        return

    # 使用多线程下载图片
    print(f"开始下载 {len(image_urls)} 张图片...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download_image, url, save_dir) for url in image_urls]
        downloaded_count = sum(1 for future in futures if future.result())

    print(f"完成！共下载 {downloaded_count} 张图片到 {save_dir}")

if __name__ == "__main__":
    main()