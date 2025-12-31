import re
from argparse import ArgumentParser, Namespace
from copy import deepcopy
from multiprocessing.pool import Pool
from time import sleep
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
import ujson as json
from loguru import logger
from pandas import date_range
from tqdm import tqdm
from trafilatura import extract, fetch_url
from trafilatura.settings import DEFAULT_CONFIG

argparser = ArgumentParser("Crawl Naver news articles")
argparser.add_argument("--output-path", type=str, default="news.json")
argparser.add_argument("--query", type=str, default="")
argparser.add_argument("--start-date", type=str, default="2025.10.01")
argparser.add_argument("--end-date", type=str, default="2025.10.21")
argparser.add_argument("--num-workers", type=int, default=10)
argparser.add_argument("--max-trials", type=int, default=3)
argparser.add_argument("--sleep-time", type=float, default=0.5)

# https://trafilatura.readthedocs.io/en/latest/settings.html
TRAFILATURA_CONFIG = deepcopy(DEFAULT_CONFIG)
# URL에 대해서 5초 이상 다운로드를 기다리지 않도록 설정
TRAFILATURA_CONFIG["DEFAULT"]["DOWNLOAD_TIMEOUT"] = "5"
# 최소 본문 길이가 50자 이상인 경우에만 사용
TRAFILATURA_CONFIG["DEFAULT"]["MIN_OUTPUT_SIZE"] = "50"


def get_article_body(url: str) -> Optional[Dict[str, Any]]:
    try:
        downloaded = fetch_url(url, config=TRAFILATURA_CONFIG)
        # 아래 인자에 대해서는 https://trafilatura.readthedocs.io/en/latest/corefunctions.html#extract 참고
        extracted_news_content = extract(
            downloaded,
            output_format="json",
            target_language="ko",
            with_metadata=True,
            deduplicate=True,
            config=TRAFILATURA_CONFIG,
        )
        if extracted_news_content is None:
            logger.warning(f"Failed to extract article from {url}: No content found")
            return None
        extracted_news_content = json.loads(extracted_news_content)
    except KeyboardInterrupt:
        exit()
    except Exception as e:
        logger.error(f"Failed to extract article from {url}: {e}")
        return None

    return extracted_news_content


def crawl_articles(args: Namespace) -> List[Dict[str, str]]:
    # Pandas date_range 함수를 사용해서 날짜 범위 생성
    dates = date_range(args.start_date, args.end_date, freq="D")

    # URL에 대한 쿼리 인코딩
    encoded_query = quote(args.query)

    crawled_urls = set()
    crawled_articles = []
    progress_bar = tqdm(total=len(dates))

    for date in dates:
        date_str = date.strftime("%Y%m%d")

        next_url = (
            "https://s.search.naver.com/p/newssearch/3/api/tab/more?"
            f"query={encoded_query}&sort=0&"
            f"nso=so%3Ar%2Cp%3Afrom{date_str}to{date_str}%2Ca%3Aall&ssc=tab.news.all&"
            f"start=1"
        )

        while True:
            num_trials = 0
            while num_trials < args.max_trials:
                try:
                    # logger.debug(f"Crawling articles for url: {next_url}")
                    response = requests.get(next_url)
                    break
                except KeyboardInterrupt:
                    # Ctrl + C 입력 시 프로그램 종료
                    exit()
                except Exception as e:
                    # 네트워크 문제 등으로 인해 요청이 실패한 경우 sleep_time 초 대기 후 재시도
                    logger.warning(f"Retrying {next_url} in {args.sleep_time} seconds...")
                    sleep(args.sleep_time)
                    num_trials += 1

            request_result = response.json()
            if request_result["collection"] is None:
                logger.warning(f"No articles found for {next_url}")
                break

            next_url = request_result["url"]
            if next_url == "":
                logger.warning("Final page reached")
                break

            script = request_result["collection"][0]["script"]
            article_urls = re.findall(r"\"contentHref\":\"(.*?)\"", script)
            with Pool(args.num_workers) as pool:
                for article_body in pool.imap_unordered(get_article_body, article_urls):
                    if article_body is not None:
                        crawled_articles.append(article_body)

            crawled_urls.update(article_urls)

            progress_bar.set_postfix({"date": date, "num_articles": len(crawled_articles)})

            sleep(args.sleep_time)

        progress_bar.update(1)

    return crawled_articles


if __name__ == "__main__":
    args = argparser.parse_args()

    crawled_articles = crawl_articles(args)

    with open(args.output_path, "w") as f:
        json.dump(crawled_articles, f, ensure_ascii=False)
