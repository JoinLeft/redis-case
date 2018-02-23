#!/usr/bin/python
# -*- coding: UTF-8 -*-

import redis, random

# 初始化reids链接
try:
    conn = redis.Redis('localhost')
except:
    print 'redis链接失败'


# 自动补全全部联系人

def add_update_contact(user, contact):
    """
    构建最近联系人自动补全列表
    :param conn:  redis链接
    :param user:    用户名
    :param contact: 联系人
    :return:
    """

    # 初始化用户联系人list键名
    ac_lsit = 'recent:' + user
    # 使用管道的原子操作
    pipeline = conn.pipeline(True)
    # 如果要查询的联系人已经存在，那么移除他
    pipeline.lrem(ac_lsit, contact)
    # 然后将联系人推入到列表的最前端
    pipeline.lpush(ac_lsit, contact)
    # 只保留列表里面的前100个联系人
    pipeline.ltrim(ac_lsit, 0, 99)
    # 发送请求
    pipeline.execute()

def remove_contact(user, contact):
    """
    移除联系人，用户在不想再看见某个联系人的时候，将指定联系人从列表中移除掉
    :param user:
    :param contact:
    :return:
    """
    conn.lrem('recent:' + user, contact)

def fetch_autocomplete_lsit(user, prefix):
    """
    获取自动补全列表并查找匹配的用户
    :param user:
    :param prefix:
    :return:
    """
    # 获取所有联系人列表, 0, -1 表示获取全部值
    candidates = conn.lrange('recent:' + user, 0, -1)
    # 初始化匹配的联系人列表，这里是 python 的列表变量
    matches = []
    # python 的 for 循环语法
    for candidate in candidates:
        # lower() 将所有字母转为小写
        # startswith() 方法用于检查字符串是否是以指定子字符串开头
        if candidate.lower().startswith(prefix):
            # 如果用户匹配成功追加到匹配成功的用户列表中
            matches.append(candidate)

    return matches

# 模拟生成 100 个用户名
for num in range(1, 100):
    # 随机的用户名长度 5-15 位
    user_name_length = random.randint(5, 15)
    name = ''
    for index in range(user_name_length):
        # 英文字母a-z对应的 ascll 码对应数字范围是 97 - 122
        name += chr(random.randint(97, 122))
    # 将生成的用户名追加到列表当中去
    # add_update_contact('jiang', name)



# 模糊查询匹配到到联系人
user_list = fetch_autocomplete_lsit('jiang', 'a')
print(user_list)


















