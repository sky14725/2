# downloader.py
import os
import requests
import queue
import threading
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import random
import retrying
from typing import Optional, Dict

# 保存路径锁，确保文件写入安全
file_lock = threading.Lock()

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
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'}
        response = requests.get(detail_url, headers=headers, timeout=10)
        response.raise_for_status()
        detail_soup = BeautifulSoup(response.text, 'html.parser')

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
        time.sleep(random.uniform(1, 3))

def download_worker(detail_queue: queue.Queue, save_dir: str) -> None:
    """
    从队列中获取详情页链接，访问详情页，提取高清图片并下载。

    Args:
        detail_queue (queue.Queue): 存放详情页链接的队列。
        save_dir (str): 保存图片的目录。
    """
    while True:
        detail_url = detail_queue.get()
        if detail_url is None:  # 收到结束信号
            detail_queue.put(None)  # 传递结束信号给其他线程
            break

        actual_url = fetch_detail_page(detail_url)
        if actual_url:
            download_image(actual_url, save_dir)

def start_downloaders(detail_queue: queue.Queue, save_dir: str, max_workers: int) -> list[threading.Thread]:
    """
    启动多个下载线程。

    Args:
        detail_queue (queue.Queue): 存放详情页链接的队列。
        save_dir (str): 保存图片的目录。
        max_workers (int): 最大线程数。

    Returns:
        list[threading.Thread]: 下载线程列表。
    """
    threads = []
    for _ in range(max_workers):
        thread = threading.Thread(target=download_worker, args=(detail_queue, save_dir))
        thread.start()
        threads.append(thread)
    return threads

def main():
    print("欢迎使用简易网页图片下载器（基于EasySpider的图片处理逻辑）")
    url = input("请输入要下载图片的网页URL（例如 https://example.com）：").strip()
    save_dir = input("请输入保存图片的目录（直接回车默认为 'images'）：").strip() or "images"
    max_workers = int(input("请输入最大线程数（默认 5）：").strip() or 5)
    max_pages = int(input("请输入最大翻页次数（默认 5）：").strip() or 5)

    if not url.startswith('http://') and not url.startswith('https://'):
        print("错误：URL必须以 http:// 或 https:// 开头")
        return

    # 创建保存目录
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 创建队列
    detail_queue = queue.Queue()

    # 启动下载线程
    download_threads = start_downloaders(detail_queue, save_dir, max_workers)

    # 启动爬虫线程
    from crawler import crawl_images
    crawl_thread = threading.Thread(target=crawl_images, args=(url, detail_queue, max_pages))
    crawl_thread.start()

    # 等待爬虫线程完成
    crawl_thread.join()

    # 等待下载线程完成
    for thread in download_threads:
        thread.join()

    print(f"完成！图片已下载到 {save_dir}")

if __name__ == "__main__":
    main()