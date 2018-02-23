#!/usr/bin/python
# -*- coding: UTF-8 -*-

# 通讯录自动补全功能
# 通过模糊匹配最近联系人功能我们可以看到通过 程序去查询前缀来查找相似前缀的最近联系人列表，但是如果是通讯录自动补全的话因为用户数量比较大
# 我们无法直接获取成千上完的元素到程序中进行匹配，这样会有大量的内存开销，因此下边的工作就是在 redis 内部完成查找匹配元素的工作。

"""
场景，假设用于游戏用户名的搜索，用户在不同的游戏区或者游戏公会，我们以这个先对所有的用户做一个粗精度的拆分，但是这时候一次性查询所有
用户数据仍然会有程序和redis的交互数据过大的问题，我们将使用有序集合来直接在 Redis 内部完成自动补全的前缀计算工作。
这时候你可能会不明白为什么要选择有序集合来存储自动补全列表，下面简单说一下
在大多数情况下，我们使用有序集合是为来快速地判断某个元素是否存在于有序集合里边、查看某个成员在有序集合中的位置或索引，以及从有序集合的某个地方
快速地按范围取出多个元素。然而这一次，我们将把有序集合里面的所有分值都设置为 0
这种做法使得我们可以使用有序集合的另外一个特性：当所有成员当分值都相同时，有序集合根据成员都名字来进行排序；而当所有成员当分值都是 0 的时候，
成员将按照字符串的二进制顺序进行排序。为了执行自动补全操作，程序会以小写字母的方式插入联系人的名字，并且为了方便起见，程序规定用户的名字只能包含英文字母
，这样的话就不需要考虑如何处理数字或者符号了，当然你也可以在此基础上增加数字或者符号支持

实现思路：
    假设用户是类似 abc、abca、abcd、.....、abd 这样的有序字符串序列，那么查找带有 abc 前缀的单词实际上就是查找介于 abbz 之后和abd 之前的字符串。
    如我我们知道第一个排在 abbz 之前的元素的排名以及第一个排在 abd 之后的元素的排名，那么就可以用一个 zrange 调用来取得所有介于 abbz 和 abd之间的与元素，
    而问题就在于我们并不知道那两个元素的具体排名。为来解决这个问题，我们需要向有序集合分别插入两个元素，一个元素排在 abbz 的后面
    而另外一个元素则排在 abd 的前面，接着根据这两个元素的排名来调用 zrange 命令，最后移除被插入的两个元素。

    因为在 ascii 编码（具体可以参考ascii编码表）里面，排在 z 后面的第一个字符就是左花括号 { ，所以我们只要将 { 拼接到 abc 前缀到末尾
    就可以得出元素 abc{ ，这个元素即位于 abc 之前，又位于所有带有 abc 前缀到合法名字之后。同样的，只要将 { 追加到 abb 到末尾，就可以得出元素 abb{
    这个元素位于所有带有 abc 前缀的合法名字之前，可以按范围查找所有带有abc前缀的名字时，将其用做起始元素。另一方面，因为在 ascii 编码里边
    第一个排在 a 前面的字符就是反引号 ` ，所以如果我们要查找的是带有 aba 的前缀的名字，而不是带有 abc 前缀的名字，那么可以使用 ab` 作为范围查找的起始元素
    并将 aba { 用作范围查找的结束元素。

    假设我要查找 aba 前缀的用户名， 起始位置是 ab`，结束位置 aba{
    中间可能存在的用户名 ab` 开始「 aba abab abac abaz  」aba{ 结束

    综上所述，通过将给定前缀的最后一个字符替换为第一个排在该字符前面的字符，可以得到前缀的前驱，而通过给前缀的末尾拼接上左花括号，可以得到前缀的后驱
    为了防止多个前缀搜索同时进行时出现任何问题，程序还会给前缀拼接一个左花扩展，以便在有需要的时候，根据这个左花括号来过滤掉被插入有序集合里面的起始元素和结束元素
    具体怎么理解将通过代码解释
"""
# 引入二分搜索库
import bisect
# 引入 uuid
import uuid

import redis

# 初始化reids链接
try:
    conn = redis.Redis('localhost')
except:
    print 'redis链接失败'

# 初始化一个由已知字符组成的列表
valid_characters = '`abcdefghijklmnopqrstuvwxyz{'

def find_prefix_range(prefix):
    """
    获取查询字符串的前后缀，假设 'abcdef' ，返回值 ('abcdee{', 'abcdef{')
    :param prefix:
    :return:
    """
    # prefix[-1:] 是获取字符串的最后一个元素
    # bisect_left 查找上边获取到最后一个元素在已知字符中到左边位置
    # 在字符列表中查找前缀字符串所处的位置
    posn = bisect.bisect_left(valid_characters, prefix[-1:])
    # 根据位置找到前驱字符串
    # posn or 1  逻辑运算判断，如果 pson 的值存在 则返回 pson 的值，如果不存在则返回 1
    suffix = valid_characters[(posn or 1) - 1]
    # prefix[:-1] 截取查询字符中从 0 到 -1 到字符串
    return prefix[:-1] + suffix + '{', prefix + '{'

# print find_prefix_range('abcdef')
# 这里只能处理 a-z 的字符串，更复杂的字符后续完善

"""
上边完成了前缀的获取之后，接下来的工作就是把前后缀插入到redis的有序集合中来生成查询范围
需要注意的有几点：
1：为了防止一个用户通过搜索用户名前缀来骚然其他用户，我们这里限制前缀搜索结果只显示前 10 个
2：为了自动补全程序在多个用户同时搜索一个公会成员时，将多个相同的起始元素和结束元素重复地添加到有序集合里面，或者错误地从有序集合里面移除了
    由其它用户搜索进程添加到起始元素和结束元素，自动补全程序会将一个随机生成到128位全局唯一标识符（UUID）添加到起始元素和结束元素到后面
3：另外自动补全程序还会在插入起始元素和结束元素之后，通过使用 WATCH MULTI EXEC 来确保有序集合不会在进行范围查找和范围取值期间发生变化
下面是实现代码
"""

def autocomplete_on_prefix(guild, prefix):
    """
    自动补全查询
    :param guild: 分组id，例如游戏中的公会id
    :param prefix: 查询字符串
    :return:
    """
    # 生成搜索字符串的前后缀
    start, end = find_prefix_range(prefix)
    # 根据给定的前缀计算出查找范围的起点和终点，
    identifier = str(uuid.uuid4())
    start += identifier
    end += identifier
    zset_name = 'game:1' + guild

    # 将范围的起始元素和结束元素添加到有序集合里面, 0 代表分值
    conn.zadd(zset_name, start, 0, end, 0)
    pipeline = conn.pipeline(True)
    # 这里我们使用了循环，然后在循环里边进行 watch 监听，但是随着负载对增加，程序进行重试对次数可能会越来越多，导致资源被白白浪费。后边会通过 锁 进行优化
    while 1:
        try:
            pipeline.watch(zset_name)
            # 返回前缀的排序值
            sindex = pipeline.zrank(zset_name, start)
            # 返回后缀的排序值
            eindex = pipeline.zrank(zset_name, end)
            # 计算需要取值的最大范围，我们采用上边说到的方案，如果数据量比较大的情况下，我们只截取前十个
            # min() 函数求给定值的最小值
            # eindex - 2 为什么要减 2 ，因为 减1 是当前后缀的位置， 减2 是当前所要搜索的最后一个元素的排序，不包括后缀本身
            erange = min(sindex + 9, eindex - 2)
            pipeline.multi()
            # 计算过位置之后就不需要后缀了
            pipeline.zrem(zset_name, start, end)
            # 通过 range 命令获取范围内的值
            pipeline.zrange(zset_name, sindex, erange)
            # 这里加了 -1 是为了获取列表的所有元素
            items = pipeline.execute()[-1]
            break
        except redis.exceptions.WatchError:
            # 如果自动补全有序集合已经被其他客户端修改过了，那么重试
            continue
    # 过滤掉查询结果中其他人插入的前后缀
    # for...[if]...语句一种简洁的构建List的方法
    return [item for item in items if '{' not in item]


# print autocomplete_on_prefix('', 'abcd')


# 当然还有用户加入公会和用户离开公会时的 zadd 和 zrem 操作，这里就是对集合增加和删除元素，这里不在实现
