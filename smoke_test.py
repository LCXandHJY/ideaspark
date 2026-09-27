# -*- coding: utf-8 -*-
"""IdeaSpark smoke test - run against http://127.0.0.1:5050"""
import http.cookiejar
import re
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:5050"
cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                 urllib.request.HTTPRedirectHandler())
# 不自动跟随重定向，便于检查 Location
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a):
        return None
op_nr = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), NoRedirect())

ok, fail = [], []
def check(name, cond, extra=""):
    (ok if cond else fail).append(name + (f" [{extra}]" if extra else ""))
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))

def get(path, opener=None, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {})
    try:
        r = (opener or op).open(req, timeout=30)
        return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore"), dict(e.headers)

def post(path, data, opener=None, headers=None):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body, headers=headers or {})
    try:
        r = (opener or op).open(req, timeout=30)
        return r.status, r.read().decode("utf-8"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "ignore"), dict(e.headers)

def csrf_of(html):
    m = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    return m.group(1) if m else None

# 1. 注册页 + token
s, html, _ = get("/register")
token = csrf_of(html)
check("注册页可访问且带CSRF", s == 200 and bool(token))

# 2. 无 token 注册应 400
s, _, _ = post("/register", {"username": "noforget", "password": "abc12345"}, op_nr)
check("无CSRF注册被拒(400)", s == 400, str(s))

# 3. 带 token 注册
uname = "t" + str(int(time.time()))
s, _, h = post("/register", {"_csrf": token, "username": uname, "password": "abc12345"}, op_nr)
check("带CSRF注册成功(302)", s == 302, str(s))

# 4. 新建想法过短 -> 回首页带 flash
s, home, _ = get("/")
token = csrf_of(home)
s, _, h = post("/project/new", {"_csrf": token, "name": "短想法", "idea": "太短"}, op_nr)
check("短想法被重定向", s == 302 and h.get("Location", "").endswith("#new"), h.get("Location", ""))
s, home, _ = get("/")
check("短想法flash提示", "至少写 10 个字" in home)

# 5. XSS 项目
s, _, h = post("/project/new", {"_csrf": token, "name": "<script>alert(1)</script>",
    "idea": "帮助自由职业者管理客户报价，解决报价混乱跟进难的问题", "audience": "自由职业者"}, op_nr)
loc = h.get("Location", "")
pid = re.search(r"/project/(\d+)", loc).group(1)
check("XSS项目已创建", s == 302 and bool(pid), loc)

# 6. 跑完 SSE
s, stream, _ = get(f"/project/{pid}/stream")
check("SSE产出完成", "event: done" in stream and "落地页双方案" in stream, f"{len(stream)}B")

# 7. 采纳 A（需新 token）
s, ws, _ = get(f"/project/{pid}")
token = csrf_of(ws)
s, _, h = post(f"/project/{pid}/choose/200", {"_csrf": token}, op_nr)
check("非法版本号被拒(404)", s == 404)
# 找到真实版本id
vid = re.search(r"/choose/(\d+)", ws).group(1)
s, _, h = post(f"/project/{pid}/choose/{vid}", {"_csrf": token}, op_nr)
check("采纳方案跳转#iterate", s == 302 and h.get("Location", "").endswith("#iterate"))

# 8. 未识别指令 -> 待办
s, ws, _ = get(f"/project/{pid}")
token = csrf_of(ws)
s, _, _ = post(f"/project/{pid}/iterate", {"_csrf": token, "cmd": "帮我接入微信支付并做个抽奖转盘"}, op_nr)
s, ws2, _ = get(f"/project/{pid}")
check("未识别指令进入待办", "抽奖转盘" in ws2 and "需求待办" in ws2)

# 9. XSS 预览检查转义
s, preview, _ = get(f"/project/{pid}/preview/{vid}")
check("XSS脚本被转义", "<script>alert(1)</script>" not in preview and "&lt;script&gt;" in preview)

# 10. 发布 + 爬虫不过滤计数
s, ws, _ = get(f"/project/{pid}")
token = csrf_of(ws)
s, _, _ = post(f"/project/{pid}/publish", {"_csrf": token}, op_nr)
s, ws, _ = get(f"/project/{pid}")
slug = re.search(r'/p/([a-z0-9]+)', ws).group(1)
s, stats_before, _ = get(f"/project/{pid}/stats.json")
import json
b = json.loads(stats_before)
time.sleep(1.1)
ua = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}
get(f"/p/{slug}", headers=ua)
get(f"/p/{slug}", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"})
s, stats_after, _ = get(f"/project/{pid}/stats.json")
a = json.loads(stats_after)
check("爬虫UA不计数/真人计数", a["views"] == b["views"] + 1, f'{b["views"]}->{a["views"]}')

# 11. 蜜罐订阅不入库
s, sub_before, _ = get(f"/project/{pid}/stats.json")
b = json.loads(sub_before)
s, _, _ = post(f"/p/{slug}/subscribe", {"email": "spam@x.com", "website": "http://spam"}, op_nr)
s, sub_after, _ = get(f"/project/{pid}/stats.json")
a = json.loads(sub_after)
check("蜜罐垃圾订阅被丢弃", a["leads"] == b["leads"])

# 12. 正常订阅入库
s, _, _ = post(f"/p/{slug}/subscribe", {"email": "real@user.com", "website": ""}, op_nr)
s, sub_after, _ = get(f"/project/{pid}/stats.json")
a = json.loads(sub_after)
check("真实订阅入库", a["leads"] == b["leads"] + 1)

# 13. 删除项目（关联数据一并清）
s, ws, _ = get(f"/project/{pid}")
token = csrf_of(ws)
s, _, h = post(f"/project/{pid}/delete", {"_csrf": token}, op_nr)
check("删除项目成功", s == 302)
s, gone, _ = get(f"/project/{pid}")
check("删除后404", s == 404)

print(f"\n==== {len(ok)} passed, {len(fail)} failed ====")
if fail:
    print("FAILED:", fail)
