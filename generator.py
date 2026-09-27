"""IdeaSpark - virtual founding team generation engine.

No external LLM: a deterministic procedural engine that parses the idea,
detects sector/audience, and composes artifacts + a real landing page spec.
Designed so a real LLM can later replace `compose_*` behind the same API.
"""
import hashlib
import json
import re

from markupsafe import escape

# ---------------------------------------------------------------- parsing

SECTORS = [
    (("教育", "学习", "课程", "学生", "老师", "培训", "英语", "考试"), "在线教育",
     {"tam": "中国在线教育市场约 5000 亿元，年增速 12%",
      "comps": ["得到", "网易云课堂", "腾讯课堂(已关停留下的空档)", "多邻国(语言类)"],
      "chan": ["小红书笔记种草", "B站知识区投放", "校园大使裂变"]}),
    (("电商", "购物", "卖货", "商城", "团购", "二手", "闲置"), "电商零售",
     {"tam": "中国网络零售市场约 15 万亿元，直播/私域增速 20%+",
      "comps": ["拼多多", "闲鱼", "微店", "快团团"],
      "chan": ["抖音短视频带货", "微信社群裂变", "KOC 测评"]}),
    (("健康", "健身", "运动", "医疗", "睡眠", "减肥", "心理", "情绪", "打卡", "习惯", "自律", "早起"), "健康身心",
     {"tam": "中国大健康市场约 10 万亿元，数字健康年增速 25%",
      "comps": ["Keep", "薄荷健康", "简单心理", "潮汐"],
      "chan": ["小红书打卡挑战", "企业团购福利", "线下健身房联营"]}),
    (("记账", "财务", "理财", "预算", "报销", "发票"), "个人财务",
     {"tam": "中国个人理财工具用户超 3 亿，付费意愿逐年上升",
      "comps": ["随手记", "鲨鱼记账", "MoneyThings", "Notion 模板作者"],
      "chan": ["效率工具榜单测评", "V2EX/即刻社区冷启动", "公众号干货引流"]}),
    (("社交", "社区", "交友", "匹配", "脱单"), "社交社区",
     {"tam": "中国陌生人社交市场约 700 亿元，细分场景仍有机会",
      "comps": ["Soul", "青藤之恋", "即刻", "Discord 群组"],
      "chan": ["高校社团地推", "话题事件营销", "种子用户邀请制"]}),
    (("游戏", "电竞", "陪玩", "卡牌"), "游戏娱乐",
     {"tam": "中国游戏市场约 3000 亿元，休闲小游戏增速显著",
      "comps": ["腾讯游戏", "网易游戏", "TapTap 独立游戏", "Steam 独立发行"],
      "chan": ["B站实况视频", "TapTap 预约", "主播试玩合作"]}),
    (("旅行", "旅游", "出行", "酒店", "攻略"), "旅行出行",
     {"tam": "中国在线旅游市场约 1.2 万亿元，自由行占比持续提升",
      "comps": ["马蜂窝", "携程", "小红书攻略", "穷游"],
      "chan": ["目的地话题 SEO", "旅行博主共创", "节假日 Campaign"]}),
    (("宠物", "猫", "狗", "萌宠"), "宠物经济",
     {"tam": "中国宠物市场约 3500 亿元，年增速 15%",
      "comps": ["波奇宠物", "E宠", "小佩", "它基金社群"],
      "chan": ["萌宠短视频", "宠物医院合作", "社群晒图裂变"]}),
    (("美食", "餐饮", "外卖", "食谱", "做饭", "咖啡"), "餐饮美食",
     {"tam": "中国餐饮市场约 5 万亿元，家庭厨房场景升温",
      "comps": ["下厨房", "豆果美食", "美团", "懒饭"],
      "chan": ["菜谱短视频", "本地生活达人探店", "社群拼团"]}),
    (("ai", "gpt", "大模型", "智能", "agent", "自动化"), "AI 应用",
     {"tam": "全球 AI 应用市场 2026 年预计超 3000 亿美元，为增速最快赛道",
      "comps": ["ChatGPT 生态插件", "Coze/扣子", "Dify", "垂直 AI 工具群"],
      "chan": ["Product Hunt 首发", "X/Twitter Build in Public", "AI 导航站收录"]}),
]

DEFAULT_SECTOR = ("效率工具", {
    "tam": "全球生产力软件市场约 6000 亿元，细分工具频出爆款",
    "comps": ["Notion", "飞书", "flomo", "各类垂类小工具"],
    "chan": ["效率社区测评", "SEO 长尾词", "口碑邀请返利"]})


def detect_sector(idea):
    text = idea.lower()
    for keys, name, meta in SECTORS:
        if any(k in text for k in keys):
            return name, meta
    return DEFAULT_SECTOR


def extract_audience(idea):
    # 排除「帮我做...」这类，只在「帮/给/为/面向/帮助/服务于」后接真实人群时命中
    m = re.search(
        r"(?:面向|为了?|帮助|服务于?|帮(?!我)|给(?!我|你|他|她)|让(?!我)|使)\s*"
        r"([一-龥A-Za-z0-9]{2,16}?)"
        r"(?:人群|用户|们|提供|解决|通过|把|用|来|帮|远程|关心|批量|整理|管理|养成|"
        r"提醒|生成|实现|完成|获得|提升|摆脱|打造|开发|设计|，|。|、|$)",
        idea)
    if m:
        return m.group(1)
    return "早期种子用户"


def extract_name(idea):
    """从一句话想法里解析产品名；解析不到则用赛道+人群生成。"""
    m = re.search(
        r"(?:做|帮我(?:做|搞|弄)?|打造|开发|设计|搞一个?|弄一个?)"
        r"(?:一个|个|一款)?"
        r"\s*([一-龥A-Za-z0-9]{2,12}?)(?:的|，|。|、|$)",
        idea)
    if m:
        name = m.group(1).strip()
        if 2 <= len(name) <= 12:
            return name
    # 兜底：赛道 + 人群生成短名
    sector, _ = detect_sector(idea)
    aud = extract_audience(idea)
    if aud != "早期种子用户":
        return f"{aud[:6]}助手"
    return sector[:6] + "工具"


def extract_pain(idea):
    m = re.search(r"(?:解决|痛点是|苦于|摆脱)\s*([^，。；]{2,40})", idea)
    if m:
        return m.group(1)
    return "现有方案成本高、体验割裂、上手门槛高"


def short_title(name):
    return name.strip()[:24] or "未命名项目"


# ---------------------------------------------------------------- artifacts

def compose_research(name, idea, audience):
    sector, meta = detect_sector(idea)
    pain = extract_pain(idea)
    lines = f"""## 市场调研卡 · {short_title(name)}

**赛道判断**：{sector}
**目标人群**：{audience}
**核心痛点**：{pain}

### 市场空间（估算）
- {meta['tam']}
- 早期可切入细分：以「{audience}」为楔子人群，单点验证后再横向扩张

### 竞品扫描
""" + "\n".join(f"- **{c}**：现有方案，差异化空间在于更聚焦的场景与更轻的交互" for c in meta["comps"]) + f"""

### 机会点
1. 围绕「{pain}」做 10 倍体验改进，而非功能堆砌
2. 利用{meta['chan'][0]}等低成本渠道完成冷启动
3. 以落地页 + 等待名单(waitlist)先验证付费意愿，再决定是否加大投入

### 风险与对策
- **需求伪命题风险**：先收集 100 个等待名单，转化率 < 5% 则 pivot
- **巨头挤压风险**：深耕细分人群语境，做巨头看不上的小切口
- **获客成本风险**：优先内容/社群渠道，预算后置

*—— Iris · 深度研究员*"""
    return "市场调研卡", lines


def compose_prd(name, idea, audience):
    sector, _ = detect_sector(idea)
    pain = extract_pain(idea)
    content = f"""## 产品需求文档（精简版） · {short_title(name)}

**一句话定位**：为「{audience}」解决「{pain}」的{sector}产品。

### 用户故事
1. 作为{audience}，我希望在 30 秒内理解这个产品能帮我什么，以便决定是否继续了解
2. 作为{audience}，我希望能留下邮箱获得内测资格，以便第一时间体验
3. 作为{audience}，我希望看到真实的功能规划和价格预期，以便建立信任

### MVP 功能范围
- [x] 价值主张落地页（本页，已自动生成）
- [x] 等待名单收集（邮箱订阅，已内置）
- [ ] 核心功能 Alpha（根据等待名单反馈排期）
- [ ] 付费试点（Stripe/微信支付，验证客单价）

### 关键指标
- 落地页访问 → 订阅转化率（目标 ≥ 8%）
- 7 日等待名单增长（目标 ≥ 100）
- 用户访谈完成数（目标 ≥ 15）

### 非目标（本期不做）
- 不做大而全的平台功能；不做原生 App（先用 Web 验证）

*—— Emma · 产品经理*"""
    return "产品需求文档", content


def compose_arch(name, idea, audience):
    content = f"""## 技术方案 · {short_title(name)}

### 架构总览
- **前端**：服务端渲染落地页（当前交付物），后续演进为 React SPA
- **后端**：Flask + SQLite（原型期）→ PostgreSQL（放量期）
- **部署**：容器化，支持一键发布与版本回退
- **数据**：用户、版本、访问事件、订阅线索分表存储，全部落盘持久化

### 数据模型（已建表）
- users / projects / artifacts（团队产出物） / versions（落地页版本快照）
- visits（访问事件流） / leads（等待名单）

### 关键设计决策
1. **版本快照制**：每次迭代存完整页面快照，任意版本可回退、可对比
2. **发布与编辑解耦**：草稿迭代不影响线上页，点「发布」才生效
3. **生成引擎可替换**：当前为规则引擎，接口预留，可平替为真实大模型

### 里程碑
- M1 落地页 + 订阅（已完成）
- M2 数据看板 + A/B 赛马（已完成）
- M3 核心功能 Alpha（视等待名单规模启动）

*—— Bob · 架构师*"""
    return "技术方案", content


def compose_growth(name, idea, audience):
    sector, meta = detect_sector(idea)
    content = f"""## 冷启动运营计划 · {short_title(name)}

### 渠道策略（按优先级）
""" + "\n".join(f"{i+1}. **{ch}**：制作 3 条内容测试点击，跑出 CTR > 3% 的素材再加投" for i, ch in enumerate(meta["chan"])) + f"""

### 两周节奏
- D1-D3：发布落地页，邀请 20 个目标用户体验并访谈
- D4-D7：根据访谈迭代价值主张与首屏文案（用「对话迭代」功能直接改）
- D8-D14：渠道小规模投放，观察看板转化漏斗

### SEO 关键词建议
- {sector} 工具 / {audience} 必备 / {short_title(name)} 评测

### 转化文案钩子
- 强调「{extract_pain(idea)}」的解决前后对比
- 早鸟权益：前 100 名订阅用户终身 5 折

*—— Sarah · 增长运营*"""
    return "冷启动运营计划", content


# ---------------------------------------------------------------- landing page spec

FEATURE_BANK = {
    "默认": [
        ("分钟级上手", "无需培训，打开即用，把学习时间还给真正重要的事"),
        ("为结果负责", "每一项功能都指向可衡量的业务指标，而非花瓶式堆砌"),
        ("持续迭代", "基于真实用户反馈双周更新，产品与你一起成长"),
    ],
    "在线教育": [
        ("个性化学习路径", "根据起点与目标自动规划，拒绝千人一面"),
        ("碎片化学习", "通勤 10 分钟也能完成一个闭环小节"),
        ("学习数据可视", "进步看得见，坚持有反馈"),
    ],
    "电商零售": [
        ("一键上架", "30 秒完成商品发布，手机端全搞定"),
        ("私域沉淀", "买家自动入群，复购不再靠运气"),
        ("经营看板", "今日销量、爆款、回头客一目了然"),
    ],
    "健康身心": [
        ("科学计划", "基于权威指南生成个性化方案"),
        ("打卡激励", "连胜机制让坚持变成游戏"),
        ("数据洞察", "趋势图表读懂自己的身体"),
    ],
    "AI 应用": [
        ("自然语言驱动", "会说话就会用，零学习成本"),
        ("多模型择优", "自动选择最适合任务的模型"),
        ("隐私优先", "数据本地优先存储，可控可导出"),
    ],
}


def _features_for(sector, idea, audience):
    pain = extract_pain(idea)
    feats = list(FEATURE_BANK.get(sector, FEATURE_BANK["默认"]))
    feats[0] = (feats[0][0], feats[0][1] + f"，直面「{pain}」")
    return [{"t": t, "d": d} for t, d in feats]


# ---------------------------------------------------------------- interactive app
# 选择方案后，落地页不再只是等待名单，而是按产品类型生成真实可交互的功能模块。
# 每个 app 是纯前端 HTML+JS，发布后即可使用。

def build_app(sector, idea):
    """Return {label, html, js} for an interactive mini-tool matching the sector."""
    pain = extract_pain(idea)
    # ---- 教育：复习计划生成器 ----
    if sector == "在线教育" or any(k in idea for k in ("考研", "考试", "复习", "学习计划")):
        html = '''<div class="app-box">
  <div class="app-row">
    <label>考试日期 <input type="date" id="e_date"></label>
    <label>科目数量 <input type="number" id="e_n" value="4" min="1" max="10"></label>
    <button onclick="genPlan()">生成复习计划</button>
  </div>
  <div id="plan_out" class="app-out"></div>
</div>'''
        js = r'''function genPlan(){
  var d=document.getElementById('e_date').value,n=parseInt(document.getElementById('e_n').value)||4,out=document.getElementById('plan_out');
  if(!d){out.innerHTML='<p class="hint">请先选择考试日期</p>';return;}
  var days=Math.max(1,Math.round((new Date(d)-new Date())/86400000));
  var stages=[{name:'基础阶段',ratio:0.5},{name:'强化阶段',ratio:0.3},{name:'冲刺阶段',ratio:0.2}];
  var html='<p class="hint">距考试还有 <b>'+days+'</b> 天，已为你规划 3 个阶段：</p><table><tr><th>阶段</th><th>天数</th><th>每日任务</th></tr>';
  stages.forEach(function(s){var sd=Math.max(1,Math.round(days*s.ratio));html+='<tr><td>'+s.name+'</td><td>'+sd+'天</td><td>每科 '+(sd>30?2:3)+' 小时，含 '+n+' 科轮复习 + 真题</td></tr>';});
  html+='</table><p class="hint">💡 完整计划将保存到你的账号，可按天打卡</p>';
  out.innerHTML=html;
}'''
        return {"label": "复习计划生成器", "html": html, "js": js}

    # ---- 内容/AI：标题生成器 ----
    if sector == "AI 应用" or any(k in idea for k in ("标题", "文案", "小红书", "公众号", "创作")):
        html = '''<div class="app-box">
  <div class="app-row">
    <input type="text" id="t_kw" placeholder="输入关键词，如：考研英语">
    <button onclick="genTitles()">生成 10 个标题</button>
  </div>
  <div id="t_out" class="app-out"></div>
</div>'''
        js = r'''function genTitles(){
  var kw=document.getElementById('t_kw').value.trim(),out=document.getElementById('t_out');
  if(!kw){out.innerHTML='<p class="hint">请输入关键词</p>';return;}
  var tpls=['{k}别再硬扛了，这个方法帮你省下一半时间','3个{k}技巧，第2个绝了','为什么你的{k}总是没效果？答案在这','{k}从入门到精通，看这一篇就够了','我用了7天{k}，发现了这些真相','{k}避坑指南：这5个错误别再犯','月薪3k和30k的{k}，差在哪','{k}速成：每天15分钟，21天见效','别再搜{k}了，这篇讲透了','{k}的底层逻辑，90%的人都搞错'];
  var html='<p class="hint">以下是为「'+kw+'」生成的 10 个标题：</p><ol>';
  tpls.forEach(function(t,i){html+='<li>'+t.replace(/\{k\}/g,kw)+'</li>';});
  html+='</ol><p class="hint">💡 可一键复制，生成更多风格请升级 Pro</p>';
  out.innerHTML=html;
}'''
        return {"label": "爆款标题生成器", "html": html, "js": js}

    # ---- 财务/效率：报价计算器 ----
    if sector == "个人财务" or any(k in idea for k in ("报价", "合同", "回款", "自由职业", "接单")):
        html = '''<div class="app-box">
  <div class="app-row">
    <label>项目名 <input type="text" id="q_name" placeholder="如：官网开发"></label>
    <label>工时(小时) <input type="number" id="q_h" value="40"></label>
    <label>时薪(¥) <input type="number" id="q_r" value="200"></label>
  </div>
  <div class="app-row"><button onclick="genQuote()">生成报价单</button></div>
  <div id="q_out" class="app-out"></div>
</div>'''
        js = r'''function genQuote(){
  var n=document.getElementById('q_name').value.trim()||'项目',h=parseFloat(document.getElementById('q_h').value)||0,r=parseFloat(document.getElementById('q_r').value)||0,out=document.getElementById('q_out');
  var base=h*r,fee=Math.round(base*0.1),tax=Math.round(base*0.06),total=base+fee+tax;
  out.innerHTML='<p class="hint">「'+n+'」报价单：</p><table><tr><td>基础费用 ('+h+'h × ¥'+r+')</td><td>¥'+base+'</td></tr><tr><td>服务费 10%</td><td>¥'+fee+'</td></tr><tr><td>税费 6%</td><td>¥'+tax+'</td></tr><tr class="total"><td>合计</td><td>¥'+total+'</td></tr></table><p class="hint">💡 可导出 PDF，发送给客户</p>';
}'''
        return {"label": "报价单计算器", "html": html, "js": js}

    # ---- 健康/用药：提醒表 ----
    if sector == "健康身心" or any(k in idea for k in ("吃药", "用药", "打卡", "习惯")):
        html = '''<div class="app-box">
  <div class="app-row">
    <input type="text" id="m_name" placeholder="药品/习惯名称，如：降压药">
    <input type="text" id="m_freq" placeholder="频次，如：每日3次">
    <button onclick="genReminder()">生成提醒表</button>
  </div>
  <div id="m_out" class="app-out"></div>
</div>'''
        js = r'''function genReminder(){
  var n=document.getElementById('m_name').value.trim(),f=document.getElementById('m_freq').value.trim(),out=document.getElementById('m_out');
  if(!n||!f){out.innerHTML='<p class="hint">请填写名称和频次</p>';return;}
  var slots=['08:00 早餐后','12:30 午餐后','19:00 晚餐后','21:30 睡前'];
  var num=Math.min(slots.length,Math.max(1,parseInt((f.match(/\d+/)||[3])[0])));
  var html='<p class="hint">「'+n+'」今日提醒（'+f+'）：</p><ul class="rem">';
  for(var i=0;i<num;i++){html+='<li><span class="time">'+slots[i].split(' ')[0]+'</span> '+slots[i].split(' ')[1]+' · '+n+'</li>';}
  html+='</ul><p class="hint">💡 开启通知后将按时推送提醒</p>';
  out.innerHTML=html;
}'''
        return {"label": "用药/习惯提醒表", "html": html, "js": js}

    # ---- 默认：待办清单 ----
    html = '''<div class="app-box">
  <div class="app-row">
    <input type="text" id="g_in" placeholder="输入今日目标，如：完成方案初稿">
    <button onclick="addTodo()">添加</button>
  </div>
  <ul id="g_list" class="todo"></ul>
  <p class="hint" id="g_hint">💡 已添加的任务可勾选完成，数据保存在本地</p>
</div>'''
    js = r'''function addTodo(){var v=document.getElementById('g_in').value.trim();if(!v)return;var li=document.createElement('li');li.innerHTML='<label><input type="checkbox" onchange="this.parentNode.classList.toggle(\'done\',this.checked)"> '+v+'</label>';document.getElementById('g_list').appendChild(li);document.getElementById('g_in').value='';}'''
    return {"label": "效率清单", "html": html, "js": js}


# ---------------------------------------------------------------- clarify flow

def clarify_message(name, idea, audience):
    """PM asks clarifying questions before the team builds (Astoms-style)."""
    sector, _ = detect_sector(idea)
    pain = extract_pain(idea)
    who = audience or "早期种子用户"
    return (
        f"「{short_title(name)}」至少有两种做法：可以只做给{who}用的轻量单点工具，"
        f"快速上线验证；也可以做成带社群/排行榜/多人协作的完整产品——两种做法的落地页打法、"
        f"定价和功能取舍差别很大，所以先跟你确认一下。\n\n"
        f"我初步判断这是「{sector}」方向，你最想解决的是「{pain}」。"
        f"下面几个关键配置选一下，团队会严格按你的选择生成调研、PRD 和落地方案。"
    )


def build_questions(idea, audience):
    """Rule-based clarifying questions. An LLM can replace this later."""
    sector, _ = detect_sector(idea)
    return [
        {"key": "styles", "type": "multi", "title": "落地页视觉风格（至少选一项，可两项都选做赛马）",
         "options": [
             {"value": "neo", "label": "深色科技风", "desc": "高级、酷，适合 AI / 工具类产品"},
             {"value": "mag", "label": "浅色杂志风", "desc": "温和、有质感，适合生活 / 教育类产品"}]},
        {"key": "value", "type": "single", "title": "首屏主打哪个价值主张？",
         "options": [
             {"value": "time", "label": "省时高效", "desc": "强调每天帮用户省下时间"},
             {"value": "money", "label": "省钱高性价比", "desc": "用 1/10 成本替代现有方案"},
             {"value": "result", "label": "效果保障", "desc": "直接承诺结果，适合教育/健康"},
             {"value": "emotion", "label": "懂你 / 圈层认同", "desc": "主打陪伴感和身份共鸣"}]},
        {"key": "sections", "type": "multi", "title": "落地页需要哪些板块？（多选）",
         "options": [
             {"value": "pricing", "label": "价格方案", "desc": "亮出定价，直接测试付费意愿"},
             {"value": "faq", "label": "常见问题", "desc": "消除下单/订阅前的疑虑"},
             {"value": "testimonials", "label": "用户评价", "desc": "用证言建立信任感"}]},
        {"key": "model", "type": "single", "title": "商业模式（决定价格板块怎么写）",
         "options": [
             {"value": "sub", "label": "订阅制", "desc": "按月/年付费，收入可预期"},
             {"value": "freemium", "label": "免费 + 增值", "desc": "免费用基础功能，Pro 收费"},
             {"value": "once", "label": "买断制", "desc": "一次付费，决策门槛低"},
             {"value": "service", "label": "定制服务 / 咨询", "desc": "按项目报价，适合高客单"}]},
    ]


VALUE_SLOGAN = {
    "time": "让{aud}告别「{pain}」，每天省下 1 小时",
    "money": "用 1/10 的成本，让{aud}告别「{pain}」",
    "result": "为{aud}的结果负责，彻底告别「{pain}」",
    "emotion": "懂{aud}的伙伴，陪你告别「{pain}」",
}

PRICING_PLANS = {
    "sub": [
        {"plan": "早鸟版", "price": "¥0", "per": "内测期", "items": ["全部核心功能", "优先体验新特性", "创始人直连群"]},
        {"plan": "正式版", "price": "¥29", "per": "/ 月", "items": ["早鸟版全部", "高级数据分析", "专属客服"]}],
    "freemium": [
        {"plan": "免费版", "price": "¥0", "per": "永久", "items": ["核心功能不限量", "社区支持"]},
        {"plan": "Pro", "price": "¥19", "per": "/ 月", "items": ["全部高级功能", "数据导出", "优先响应"]},
        {"plan": "团队版", "price": "¥49", "per": "/ 人 / 月", "items": ["Pro 全部", "协作空间", "管理后台"]}],
    "once": [
        {"plan": "内测名额", "price": "¥0", "per": "限 100 名", "items": ["抢先体验完整产品", "终身内测价锁定"]},
        {"plan": "终身买断", "price": "¥199", "per": "一次付费", "items": ["当前全部功能", "两年内大版本免费升级", "社群 + 客服"]}],
    "service": [
        {"plan": "免费诊断", "price": "¥0", "per": "30 分钟", "items": ["需求梳理", "可行性建议"]},
        {"plan": "标准服务", "price": "报价", "per": "按项目", "items": ["按需定制方案", "2 周交付", "30 天售后"]},
        {"plan": "企业定制", "price": "联系我们", "per": "", "items": ["私有化部署", "专属团队", "年度陪跑"]}],
}


def base_spec(name, idea, audience, style, config=None):
    config = config or {}
    sector, _ = detect_sector(idea)
    pain = extract_pain(idea)
    aud = audience or "早期种子用户"
    value = config.get("value", "time")
    slogan_tpl = VALUE_SLOGAN.get(value, VALUE_SLOGAN["time"])
    sections_cfg = config.get("sections")
    if sections_cfg is None:
        sections_cfg = ["faq", "testimonials"]
    model = config.get("model", "sub")
    app = build_app(sector, idea)
    return {
        "style": style,                    # neo | mag
        "accent": "#6c5ce7" if style == "neo" else "#e2503c",
        "title": short_title(name),
        "slogan": slogan_tpl.format(aud=aud, pain=pain),
        "sub": idea.strip()[:120],
        "pain": pain,
        "cta": "立即体验",
        "app": app,
        "features": _features_for(sector, idea, aud),
        "sections": {"pricing": "pricing" in sections_cfg,
                     "faq": "faq" in sections_cfg,
                     "testimonials": "testimonials" in sections_cfg},
        "pricing": PRICING_PLANS.get(model, PRICING_PLANS["sub"]),
        "faq": [
            {"q": "现在就能用吗？", "a": "产品处于内测期，留下邮箱即可进入等待名单，按顺序开通。"},
            {"q": "我的数据安全吗？", "a": "所有数据加密存储，支持随时导出与删除。"},
            {"q": "如何联系团队？", "a": "订阅后即可加入内测社群，与创始团队直接对话。"},
        ],
        "testimonials": [
            {"name": "内测用户 · 小林", "text": "等了很久终于有人把这件事做对了，已安利给整个部门。"},
            {"name": "种子用户 · Ada", "text": "上手零门槛，第二天就成了日常工作流的一部分。"},
        ],
    }


# ---------------------------------------------------------------- rendering

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:"PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 background:{bg};color:{fg};line-height:1.7}}
.wrap{{max-width:960px;margin:0 auto;padding:0 24px}}
.hero{{padding:110px 0 70px;text-align:center}}
.badge{{display:inline-block;padding:5px 14px;border-radius:99px;font-size:13px;
 border:1px solid {accent};color:{accent};margin-bottom:22px}}
h1{{font-size:clamp(30px,5vw,52px);line-height:1.25;letter-spacing:1px}}
h1 em{{font-style:normal;color:{accent}}}
.slogan{{margin-top:16px;font-size:clamp(16px,2.4vw,21px);opacity:.85}}
.sub{{margin:14px auto 0;max-width:640px;opacity:.6;font-size:15px}}
.cta-row{{margin-top:34px}}
form.waitlist{{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}}
input[type=email]{{padding:13px 18px;border-radius:10px;border:1px solid {bd};
 background:{card};color:{fg};width:min(320px,80vw);font-size:15px}}
button,a.btn{{padding:13px 26px;border-radius:10px;border:0;cursor:pointer;
 background:{accent};color:#fff;font-size:15px;text-decoration:none;display:inline-block}}
button:hover,a.btn:hover{{filter:brightness(1.12)}}
section{{padding:64px 0}}
h2{{text-align:center;font-size:clamp(22px,3.4vw,32px);margin-bottom:38px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:18px}}
.card{{background:{card};border:1px solid {bd};border-radius:16px;padding:26px}}
.card h3{{margin-bottom:10px;font-size:18px}}
.card p{{opacity:.7;font-size:14.5px}}
.price{{font-size:34px;color:{accent};font-weight:700;margin:8px 0}}
.price small{{font-size:14px;opacity:.6;font-weight:400}}
ul{{list-style:none}}li{{padding:4px 0;opacity:.75;font-size:14.5px}}
li::before{{content:"✓ ";color:{accent}}}
details{{background:{card};border:1px solid {bd};border-radius:12px;padding:16px 20px;margin-bottom:12px}}
summary{{cursor:pointer;font-weight:600}}
details p{{margin-top:8px;opacity:.7;font-size:14.5px}}
footer{{text-align:center;padding:40px 0 56px;opacity:.45;font-size:13px}}
.ok{{color:#3ecf8e;margin-top:14px}} .err{{color:#ff6b6b;margin-top:14px}}
.quote{{font-size:15px;opacity:.85}} .who{{margin-top:10px;font-size:13px;color:{accent}}}
.hp{{position:absolute;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none}}
.app-section{{background:{card};border:1px solid {bd};border-radius:20px;padding:34px;margin-top:40px}}
.app-section h2{{margin-bottom:6px}}
.app-sub{{text-align:center;opacity:.55;font-size:14px;margin-bottom:22px}}
.app-box .app-row{{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;align-items:flex-end;margin-bottom:18px}}
.app-box label{{display:flex;flex-direction:column;font-size:13px;opacity:.8;gap:6px}}
.app-box input[type=text],.app-box input[type=number],.app-box input[type=date]{{padding:11px 14px;border-radius:10px;border:1px solid {bd};background:{bg};color:{fg};font-size:14px;width:180px}}
.app-box button{{padding:11px 22px;border-radius:10px;border:0;cursor:pointer;background:{accent};color:#fff;font-size:14px}}
.app-out{{margin-top:8px;text-align:left}}
.app-out .hint{{opacity:.6;font-size:13.5px;margin:10px 0}}
.app-out table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:14px}}
.app-out th,.app-out td{{padding:10px 12px;border-bottom:1px solid {bd};text-align:left}}
.app-out tr.total td{{font-weight:700;color:{accent}}}
.app-out ol,.app-out ul{{padding-left:20px;line-height:2;font-size:14px}}
.app-out .rem{{list-style:none;padding:0}}
.app-out .rem li{{padding:8px 0;border-bottom:1px dashed {bd}}}
.app-out .time{{color:{accent};font-weight:600;margin-right:10px}}
.app-out .todo{{list-style:none;padding:0}}
.app-out .todo li{{padding:8px 0}}
.app-out .todo .done{{text-decoration:line-through;opacity:.4}}
</style></head><body>
<div class="wrap">
<header class="hero">
  <span class="badge">立即体验 · 无需注册</span>
  <h1>{title_html}</h1>
  <p class="slogan">{slogan}</p>
  <p class="sub">{sub}</p>
</header>
<section class="app-section">
  <h2>{app_label}</h2>
  <p class="app-sub">下方是产品的核心功能，直接用</p>
  {app_html}
</section>
<section><h2>为什么选择我们</h2><div class="grid">{features}</div></section>
{pricing}
<section><h2>他们怎么说</h2><div class="grid">{testimonials}</div></section>
{faq}
<section class="waitlist-section">
  <h2>喜欢这个工具？</h2>
  <p class="app-sub">留下邮箱，第一时间获取新功能通知</p>
  <form class="waitlist" method="post" action="{action}">
    <input type="email" name="email" required placeholder="输入邮箱获取更新">
    <input type="text" name="website" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">
    <button type="submit">通知我</button>
  </form>
  {msg}
</section>
<footer>{title} · 由 IdeaSpark 虚拟创业团队构建 · {foot_note}</footer>
</div>
<script>{app_js}</script>
</body></html>"""


def render_page(spec, slug, msg=""):
    neo = spec.get("style") == "neo"
    bg, fg = ("#0d0f1a", "#eef0ff") if neo else ("#faf7f2", "#23211f")
    card, bd = ("#161a2e", "#262b45") if neo else ("#ffffff", "#e8e2d8")
    # 主题色只允许受信任的 hex 值，防止注入
    accent = spec.get("accent", "#6c5ce7")
    if not re.fullmatch(r"#[0-9a-fA-F]{3,6}", accent):
        accent = "#6c5ce7"

    title = str(escape(spec["title"]))
    title_html = title if len(title) <= 6 else f"{title[:3]}<em>{title[3:]}</em>" if len(title) > 3 else title
    features = "".join(
        f'<div class="card"><h3>{escape(f["t"])}</h3><p>{escape(f["d"])}</p></div>'
        for f in spec["features"])
    pricing = ""
    if spec.get("sections", {}).get("pricing"):
        blocks = "".join(
            f'<div class="card"><h3>{escape(p["plan"])}</h3>'
            f'<div class="price">{escape(p["price"])}<small> {escape(p["per"])}</small></div><ul>'
            + "".join(f"<li>{escape(i)}</li>" for i in p["items"]) + "</ul></div>"
            for p in spec.get("pricing", []))
        pricing = f'<section><h2>价格方案</h2><div class="grid">{blocks}</div></section>'
    faq = ""
    if spec.get("sections", {}).get("faq"):
        blocks = "".join(
            f'<details><summary>{escape(f["q"])}</summary><p>{escape(f["a"])}</p></details>'
            for f in spec.get("faq", []))
        faq = f'<section><h2>常见问题</h2>{blocks}</section>'
    testi = ""
    if spec.get("sections", {}).get("testimonials"):
        testi = "".join(
            f'<div class="card"><p class="quote">“{escape(t["text"])}”</p>'
            f'<p class="who">{escape(t["name"])}</p></div>'
            for t in spec.get("testimonials", []))
    msg_html = ""
    if msg:
        ok = ("成功" in msg or "感谢" in msg) and "<" not in msg
        msg_html = f'<p class="{"ok" if ok else "err"}">{escape(msg)}</p>'
    app = spec.get("app") or {"label": "立即体验", "html": "", "js": ""}
    return PAGE_TEMPLATE.format(
        title=title, title_html=title_html, slogan=escape(spec["slogan"]), sub=escape(spec["sub"]),
        cta=escape(spec.get("cta", "立即体验")), features=features, pricing=pricing, faq=faq, testimonials=testi,
        bg=bg, fg=fg, card=card, bd=bd, accent=accent,
        app_label=escape(app.get("label", "立即体验")),
        app_html=app.get("html", ""),
        app_js=app.get("js", ""),
        action=f"/p/{slug}/subscribe", msg=msg_html, foot_note="v" + str(spec.get("v", 1)))


# ---------------------------------------------------------------- iteration commands

ACCENTS = {"蓝": "#3b82f6", "绿": "#10b981", "紫": "#8b5cf6", "橙": "#f97316",
           "粉": "#ec4899", "红": "#ef4444", "青": "#06b6d4", "金": "#d4a017"}


def apply_command(spec, cmd):
    """Apply a natural-language iteration command to a page spec.
    Returns (new_spec, reply, applied). Engine is rule-based by design;
    an LLM can replace this later without touching callers."""
    spec = json.loads(json.dumps(spec, ensure_ascii=False))
    c = cmd.strip()

    m = re.search(r"(?:标题|产品名|名字)\s*(?:改|换|设)?(?:成|为|是|[:：])?\s*[:：]?\s*(.+)", c)
    if m:
        spec["title"] = m.group(1).strip().lstrip("：:").strip()[:24]
        return spec, f"已将产品标题改为「{spec['title']}」", True

    m = re.search(r"(?:口号|副标题|标语|slogan)\s*(?:改|换|设)?(?:成|为|是|[:：])?\s*[:：]?\s*(.+)", c, re.I)
    if m:
        spec["slogan"] = m.group(1).strip().lstrip("：:").strip()[:60]
        return spec, f"已将口号改为「{spec['slogan']}」", True

    m = re.search(r"(?:按钮|CTA|cta)\s*(?:文案)?(?:改|换|设)?(?:成|为|是|[:：])?\s*[:：]?\s*(.+)", c)
    if m:
        spec["cta"] = m.group(1).strip().lstrip("：:").strip()[:16]
        return spec, f"已将按钮文案改为「{spec['cta']}」", True

    if re.search(r"(深色|暗色|黑夜|科技)", c):
        spec["style"] = "neo"
        return spec, "已切换为深色科技风", True
    if re.search(r"(浅色|亮色|杂志|极简|日系)", c):
        spec["style"] = "mag"
        return spec, "已切换为浅色杂志风", True
    for k, v in ACCENTS.items():
        if k in c and ("色" in c or "主题" in c):
            spec["accent"] = v
            return spec, f"已将主题色切换为{k}色系", True

    for keys, field, label in [
        (("价格", "定价", "收费"), "pricing", "价格方案"),
        (("常见问题", "问答", "faq", "FAQ"), "faq", "常见问题"),
        (("评价", "证言", "口碑"), "testimonials", "用户评价"),
    ]:
        if any(k in c for k in keys):
            if re.search(r"(加|新增|添加|加上|开启|显示)", c):
                spec["sections"][field] = True
                return spec, f"已新增「{label}」板块", True
            if re.search(r"(去掉|删除|移除|关闭|隐藏)", c):
                spec["sections"][field] = False
                return spec, f"已移除「{label}」板块", True

    m = re.search(r"(?:加|新增|添加)\s*(?:一个|个)?(?:功能|卖点|特性|亮点)[:：]?\s*(.+)", c)
    if m:
        feat = m.group(1).strip()
        spec["features"].append({"t": feat[:14], "d": f"围绕「{feat[:30]}」打造的能力，由对话迭代加入。"})
        return spec, f"已新增功能卖点「{feat[:14]}」", True

    return spec, ("暂不理解这条指令，已自动存入「需求待办」。支持的指令：改标题/口号/按钮、"
                  "切换深浅色或主题色、增删价格/FAQ/评价板块、新增功能卖点。"), False


def spec_hash(spec):
    return hashlib.md5(json.dumps(spec, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
