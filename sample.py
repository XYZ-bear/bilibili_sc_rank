# -*- coding: utf-8 -*-
import asyncio
import http.cookies
import random
from typing import *

import aiohttp

import blivedm
import blivedm.models.web as web_models

# 直播间ID的取值看直播间URL
# TEST_ROOM_IDS = [
#     22907643
# ]
TEST_ROOM_IDS = [
]

# 这里填一个已登录账号的cookie的SESSDATA字段的值。不填也可以连接，但是收到弹幕的用户名会打码，UID会变成0
#SESSDATA = '7c4852a2%2C1756875819%2Ca92dd%2A32CjBxhBlyt_EH5rT5vSfEHYOUoJAJqaXIt3gPlgXQjgZqc9ccvbNseslku3FF8HWlVSUSVmMyVkFlV19qelJpcU1lbnFJZGhTQUtRMzVNY0twTXFOWXVLWmktbjFOS2ljS0VOQzJaSF9wamZ4aDFfemdDa0RhX2JoODFZM3NOVENZX3hsU1ZOX2lRIIEC'
SESSDATA = ''

session: Optional[aiohttp.ClientSession] = None
from collections import deque

rank_data = deque()
t_data = {"del_count": 0, "insert_count": 0}

from threading import Thread
import os

async def main():
    init_session()
    try:
        await run_single_client()
        await run_multi_clients()
    finally:
        await session.close()


def init_session():
    cookies = http.cookies.SimpleCookie()
    cookies['SESSDATA'] = SESSDATA
    cookies['SESSDATA']['domain'] = 'bilibili.com'

    global session
    session = aiohttp.ClientSession()
    session.cookie_jar.update_cookies(cookies)


async def run_single_client():
    """
    演示监听一个直播间
    """
    room_id = random.choice(TEST_ROOM_IDS)
    client = blivedm.BLiveClient(room_id, session=session)
    handler = MyHandler()
    client.set_handler(handler)

    client.start()
    try:
        # 演示5秒后停止
        await asyncio.sleep(5)
        client.stop()

        await client.join()
    finally:
        await client.stop_and_close()


async def run_multi_clients():
    """
    演示同时监听多个直播间
    """
    clients = [blivedm.BLiveClient(room_id, session=session) for room_id in TEST_ROOM_IDS]
    handler = MyHandler()
    for client in clients:
        client.set_handler(handler)
        client.start()

    try:
        await asyncio.gather(*(
            client.join() for client in clients
        ))
    finally:
        await asyncio.gather(*(
            client.stop_and_close() for client in clients
        ))


class MyHandler(blivedm.BaseHandler):
    # # 演示如何添加自定义回调
    # _CMD_CALLBACK_DICT = blivedm.BaseHandler._CMD_CALLBACK_DICT.copy()
    #
    # # 看过数消息回调
    # def __watched_change_callback(self, client: blivedm.BLiveClient, command: dict):
    #     print(f'[{client.room_id}] WATCHED_CHANGE: {command}')
    # _CMD_CALLBACK_DICT['WATCHED_CHANGE'] = __watched_change_callback  # noqa

    def _on_heartbeat(self, client: blivedm.BLiveClient, message: web_models.HeartbeatMessage):
        print(f'[{client.room_id}] 心跳')

    def _on_danmaku(self, client: blivedm.BLiveClient, message: web_models.DanmakuMessage):
        print(f'[{client.room_id}] {message.uname}|{message.uid}：{message.msg}')
        #self.add_rank(message.uid, message.uname, 10, message.msg)
        
    def _on_gift(self, client: blivedm.BLiveClient, message: web_models.GiftMessage):
        print(f'[{client.room_id}] {message.uname} 赠送{message.gift_name}x{message.num}'
              f' （{message.coin_type}瓜子x{message.total_coin}）')

    # def _on_buy_guard(self, client: blivedm.BLiveClient, message: web_models.GuardBuyMessage):
    #     print(f'[{client.room_id}] {message.username} 上舰，guard_level={message.guard_level}')

    def _on_user_toast_v2(self, client: blivedm.BLiveClient, message: web_models.UserToastV2Message):
        print(f'[{client.room_id}] {message.username} 上舰，guard_level={message.guard_level}')

        global t_data
        score = t_data.get("舰长", 0)
        score and self.add_rank(message.uid, message.uname, score, "---上舰长---")

    def _on_super_chat(self, client: blivedm.BLiveClient, message: web_models.SuperChatMessage):
        print(f'[{client.room_id}] 醒目留言 ¥{message.price} {message.uname}：{message.message}')

        self.add_rank(message.uid, message.uname, message.price, message.message)

    def add_rank(self, uid, uname, score, msg):
        global rank_data
        global t_data
        find = False
        for p in rank_data:
            if p.get("id", None) == uid:
                p["score"] = p.get("score", 0) + score
                p["msg"].append(msg)
                p["is_new"] = True
                find = True
                t_data["insert_count"] += 1
                break

        if not find:
            rank_data.append({"id": uid,"name":uname, "score": score, "msg": [msg], "is_new": True})

        rank_data = deque(sorted(rank_data, key=lambda p: p.get("score", 0), reverse=True))

        with open('rank.txt', 'w', encoding='utf-8') as file:
            file.write(str(rank_data))
            file.close()

    # def _on_interact_word(self, client: blivedm.BLiveClient, message: web_models.InteractWordMessage):
    #     if message.msg_type == 1:
    #         print(f'[{client.room_id}] {message.username} 进入房间')

# flask_web_server.py
from flask import Flask, send_from_directory, jsonify, request

app = Flask(__name__, static_folder="/")

import webbrowser


@app.route('/get_rank', methods=['GET'])
def get_rank():
    # 使用 jsonify 返回 JSON 响应
    global rank_data
    global t_data
    result = {}
    result["rank"] = list(rank_data)
    result.update(t_data)
    rjson = jsonify(result)

    for p in rank_data:
        p["is_new"] = False

    return rjson

@app.route('/delete_rank', methods=['POST'])
def delete_rank():
    global rank_data
    global t_data
    data = request.get_json()
    id = data.get('id', '')
    for p in rank_data:
        if p.get("id", None) == id:
            rank_data.remove(p)
            t_data["del_count"] += 1
            break
    return jsonify({"del_count": t_data["del_count"]})
    
@app.route('/del_all', methods=['GET'])
def del_all():
        global rank_data
        global t_data

        rank_data.clear()
        t_data["del_count"] = 0
        t_data["insert_count"] = 0


        return jsonify({})

if __name__ == '__main__':
    if os.path.exists('rank.txt'):
        with open('rank.txt', 'r', encoding='utf-8') as file:
            rank_str = file.read()
            if rank_str:
                rank_data = deque(eval(rank_str)) 
            file.close()

    if os.path.exists('config.txt'):
        with open('config.txt', 'r', encoding='utf-8') as file:
            for line in file:
                line = line.strip()  # 去除每行的空白字符（包括换行符）
                if line.startswith("room_id="):
                    TEST_ROOM_IDS = [line.split("=")[1]]
                elif line.startswith("SESSDATA="):
                    SESSDATA = line.split("=")[1]
                else:
                    items = line.split("=")[1]
                    t_data[items[0]] = int(items[1])

            file.close()

    t = Thread(target=asyncio.run, args=(main(),))
    t2 = Thread(target=app.run, args=())
    
    t.start()
    t2.start()

    webbrowser.open('http://127.0.0.1:5000/index.html', new = 0)

    t.join()
    t2.join()
   
