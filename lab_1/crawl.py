import requests
import re
from trafilatura import fetch_url, extract
from urllib.parse import quote
import json
from argparse import ArgumentParser, Namespace
from pandas import date_range
from tqdm import tqdm
from typing import List, Dict, Optional, Any
from multiprocessing.pool import Pool

argparser = ArgumentParser("naver news crawling")
argparser.add_argument("--query", type=str, default="강원대")
argparser.add_argument("--start-date", type=str, default="20251001")
argparser.add_argument("--end-date", type=str, default="20251021")
argparser.add_argument("--num-processes", type=int, default=10)
argparser.add_argument("--output-path", type=str, default="output.json")


def crawl_one_news_page(url:str)-> Optional[Dict[str,Any]]:
    download = fetch_url(url)
    try:
        news_content = json.loads(
            extract(download, output_format="json", with_metadata=True)
        )
        return news_content #type is dict coz we use loads
    except TypeError:
        print(f"failed extract-{url}")
        return None


def crawl_news(args: Namespace) -> List[Dict[str, str]]: # can have any type for anything
    endcoded_query = quote(args.query)
    news_data =[]
    date_list = date_range(args.start_date, args.end_date, freq="D")

    with tqdm(total=len(date_list)) as progress_bar:
        for date in date_list:
            date_str = date.strftime("%y%m%d")
            next_url=f"https://s.search.naver.com/p/newssearch/3/api/tab/more?nso=so%3Ar%2Cp%3Afrom{date_str}to{date_str}%2Ca%3Aall&query={endcoded_query}&sort=0&spq=0&ssc=tab.news.all&start=1"

            while True:
                response = requests.get(next_url)
                response_data = response.json()
                url = response_data["url"]
                #if next_url == "":
                    #break
                if "collection" not in response_data or response_data["collection"] is None:
                    print("no found")
                    break

                script_source = response_data["collection"][0]["script"]
                news_urls = re.findall(r"\"contentHref\":\"(.*?)\"", script_source) #take only shortest pattern when put ?.

                with Pool(args.num_processes) as pool:
                    for news_content in pool.imap(crawl_one_news_page, news_urls):
                        if news_content is None:
                            continue

                        title = news_content["title"]
                        text = news_content["text"]

                        news_data.append({"title": title, "text":text})

                    next_url = response_data["url"]
                    if next_url == "":                             
                        break
                
                progress_bar.set_postfix({"crawled data": len(news_data)})
                progress_bar.update(1)

    return news_data


if __name__ == "__main__":
    args = argparser.parse_args()
    news_data = crawl_news(args)
    

    with open("output.json", encoding="utf-8") as f:
        json.dump(news_data, f, ensure_ascii=False)

