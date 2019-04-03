# -*-coding:utf-8-*-

from config import biz_name
from selenium import webdriver
import os
import json
import re
import requests
import random
import math
import time
import sqlalchemy
from datetime import datetime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, TIMESTAMP, and_

engine = sqlalchemy.create_engine("sqlite:///wechat.db")
db_base = declarative_base()

headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}
urls = {"index": "https://mp.weixin.qq.com",
        "editor": "https://mp.weixin.qq.com/cgi-bin/appmsg?t=media/appmsg_edit&action=edit&type=10&isMul=1&isNew=1&share=1&lang=zh_CN&token={token}",
        "query_biz": "https://mp.weixin.qq.com/cgi-bin/searchbiz?action=search_biz&token={token}&lang=zh_CN&f=json&ajax=1&random={random}&query={query}&begin=0&count=5",
        "query_article": "https://mp.weixin.qq.com/cgi-bin/appmsg?token={token}&lang=zh_CN&f=json&%E2%80%A65&action=list_ex&begin={begin}&count={count}&query={query}&fakeid={fakeid}&type=9"
        }


class Article(db_base):
    __tablename__ = 'article'

    id = Column(Integer, primary_key=True)
    biz = Column(Integer)
    title = Column(String(1024))
    link = Column(String(2048))
    cover = Column(String(2048))
    creation = Column(TIMESTAMP)

    def __repr__(self):
        repr_dict = {"id": self.id,
                     "biz": self.biz,
                     "title": self.title,
                     "link": self.link,
                     "cover": self.cover,
                     "creation": self.creation}
        return json.dumps(repr_dict, ensure_ascii=False)


class Biz(db_base):
    __tablename__ = 'biz'

    id = Column(Integer, primary_key=True)
    biz_name = Column(String(1024))
    biz_id = Column(String(1024))

    def __repr__(self):
        repr_dict ={"id": self.id,
                    "name": self.biz_name,
                    "fake_id": self.biz_id}
        return json.dumps(repr_dict, ensure_ascii=False)


db_base.metadata.create_all(engine)
db_session = sessionmaker(bind=engine)


class wx_crawler:
    db = db_session()
    driver = webdriver.Chrome()
    cookies = []
    token = ''
    fake_id = []
    session = requests.session()
    session.headers = headers

    def __init__(self):
        if os.path.exists('cookies.json'):
            self.cookies = json.load(open('cookies.json', 'rb'))
        self.driver.get(urls['index'])
        if not self.cookies:
            input("Press ENTER after log into the wechat public platform")
            self.cookies = self.driver.get_cookies()
            open('cookies.json', 'wb').write(json.dumps(self.cookies).encode('utf-8'))

        for each in self.cookies:
            self.driver.add_cookie(each)
            self.session.cookies[each['name']] = each['value']

        self.driver.get(urls['index'])
        if 'token' in self.driver.current_url:
            self.token = re.findall(r'token=(\w+)', self.driver.current_url)[0]
        else:
            raise Exception("Get token failed")

        for fake_name in biz_name:
            print("Searching {fake}".format(fake=fake_name))
            resp = self.session.get(urls["query_biz"].format(random=random.random(),
                                                         token=self.token,
                                                         query=fake_name,))

            resp = json.loads(resp.text)
            if not resp["base_resp"]["ret"] == 0:
                raise Exception("Request failed")
                break
            success = False
            for biz in resp['list']:
                if fake_name == biz["nickname"]:
                    print("found biz {fake}".format(fake=fake_name))
                    print(biz["fakeid"])
                    self.fake_id.append({"name": fake_name, "id": biz["fakeid"]})
                    success = True
                    if not self.db.query(Biz).filter_by(biz_name=fake_name).first():
                        db_biz = Biz(biz_name=fake_name, biz_id=biz["fakeid"])
                        self.db.add(db_biz)
                        self.db.commit()
            if not success:
                raise Exception("find biz {fake} failed".format(fake=fake_name))

    def get_articles(self):
        result = {}
        for fake in self.fake_id:
            resp = self.session.get(urls["query_article"].format(token=self.token, fakeid=fake["id"], count=5, query='', begin=0))
            resp = json.loads(resp.text)
            result[fake["name"]] = {"articles": []}
            if resp["base_resp"]["ret"] == 0:

                total_article = resp["app_msg_cnt"]
                total_pages = int(math.ceil(total_article/5))

                for i in range(0, total_pages):
                    time.sleep(5)
                    print(i)
                    resp = self.session.get(urls["query_article"].format(token=self.token, fakeid=fake["id"], count=5, begin=i*5, query=''))
                    resp = json.loads(resp.text)

                    if resp["base_resp"]["ret"] == 0:
                        for article in resp["app_msg_list"]:
                            article_info = dict()
                            article_info["cover"] = article["cover"]
                            article_info["link"] = article["link"]
                            article_info["title"] = article["title"]
                            article_info["creation"] = article["update_time"]

                            if not self.db.query(Article).filter(
                                    and_(Article.title == article_info["title"], Article.biz == fake["name"])).first():
                                db_article = Article(biz=fake["name"], title=article_info["title"], link=article_info["link"],
                                                     cover=article_info["cover"],
                                                     creation=datetime.fromtimestamp(article_info["creation"]))

                                self.db.add(db_article)
                                self.db.commit()
                            result[fake["name"]]["articles"].append(article_info)
            else:
                print(resp)
                raise Exception("Request failed")
        open('result.json', 'wb').write(json.dumps(result, indent=4, ensure_ascii=False).encode('utf-8'))
        return result

