"""IdeaSpark - mini AI virtual founding team. Flask app."""
import hashlib
import json
import os
import re
import secrets
import time

from flask import (Flask, Response, abort, flash, get_flashed_messages,
                   jsonify, redirect, render_template, request, session,
                   url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import generator as gen

app = Flask(__name__)
app.secret_key = os.environ.get("IDEASPARK_SECRET") or secrets.token_hex(32)

# 免 CSRF 的端点（公开落地页订阅：匿名表单，用蜜罐 + 邮箱去重防护）
CSRF_EXEMPT = {"subscribe"}

BOT_UA = ("bot", "spider", "crawler", "slurp", "facebookexternalhit",
          "embedly", "quora link preview", "pinterest", "bingpreview",
          "googlebot", "baiduspider", "bytespider", "yisouspider",
          "semrushbot", "ahrefsbot", "mj12bot", "dotbot", "petalbot",
          "headless", "python-requests", "curl", "wget", "monitor")

AGENTS = [
    ("iris", "Iris · 深度研究员", "市场调研卡", gen.compose_research),
    ("emma", "Emma · 产品经理", "产品需求文档", gen.compose_prd),
    ("bob", "Bob · 架构师", "技术方案", gen.compose_arch),
    ("sarah", "Sarah · 增长运营", "冷启动运营计划", gen.compose_growth),
]


# ------------------------------------------------------------- helpers

def current_user():
    if "uid" not in session:
        return None
    return db.q("SELECT * FROM users WHERE id=?", (session["uid"],), one=True)


def get_project(pid, must_own=True):
    p = db.q("SELECT * FROM projects WHERE id=?", (pid,), one=True)
    if not p:
        abort(404)
    if must_own and (not current_user() or p["user_id"] != current_user()["id"]):
        abort(403)
    return p


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def ip_hash(ip):
    return hashlib.md5((ip or "?").encode()).hexdigest()[:10]


@app.template_filter("datetime")
def fmt_ts(ts):
    return time.strftime("%m-%d %H:%M", time.localtime(ts))


@app.before_request
def csrf_protect():
    if request.method == "POST" and request.endpoint not in CSRF_EXEMPT:
        token = session.get("_csrf", "")
        sent = request.form.get("_csrf", "")
        if not token or not sent or not secrets.compare_digest(token, sent):
            abort(400, description="表单已过期或无效，请返回重试。")


@app.context_processor
def inject_user():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(32)
    return {"me": current_user(), "csrf_token": session["_csrf"]}


# ------------------------------------------------------------- auth & home

@app.route("/")
def home():
    projects = []
    if current_user():
        projects = db.q("""
            SELECT p.*,
              (SELECT COUNT(*) FROM visits v WHERE v.project_id=p.id) AS views,
              (SELECT COUNT(*) FROM leads l WHERE l.project_id=p.id) AS leads
            FROM projects p WHERE p.user_id=? ORDER BY p.id DESC""",
            (current_user()["id"],))
    return render_template("home.html", projects=projects)


@app.route("/register", methods=["GET", "POST"])
def register():
    err = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not re.fullmatch(r"[一-龥\w]{2,20}", u):
            err = "用户名需为 2-20 位中英文/数字"
        elif len(p) < 6:
            err = "密码至少 6 位"
        elif db.q("SELECT id FROM users WHERE username=?", (u,), one=True):
            err = "用户名已被占用"
        else:
            uid = db.execute("INSERT INTO users(username,pw_hash,created_at) VALUES(?,?,?)",
                             (u, generate_password_hash(p), db.now()))
            session["uid"] = uid
            return redirect(url_for("home"))
    return render_template("auth.html", mode="register", err=err)


@app.route("/login", methods=["GET", "POST"])
def login():
    err = ""
    if request.method == "POST":
        u = db.q("SELECT * FROM users WHERE username=?",
                 (request.form.get("username", "").strip(),), one=True)
        if u and check_password_hash(u["pw_hash"], request.form.get("password", "")):
            session["uid"] = u["id"]
            return redirect(url_for("home"))
        err = "用户名或密码不正确"
    return render_template("auth.html", mode="login", err=err)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ------------------------------------------------------------- project lifecycle

@app.route("/project/new", methods=["POST"])
def new_project():
    if not current_user():
        return redirect(url_for("login"))
    raw = request.form.get("idea", "").strip()
    if len(raw) < 6:
        flash("想法至少写 6 个字，AI 才能识别产品名、人群和痛点。", "err")
        return redirect(url_for("home") + "#new")
    name = gen.extract_name(raw)
    audience = gen.extract_audience(raw)
    idea = raw
    pid = db.execute(
        "INSERT INTO projects(user_id,name,idea,audience,slug,created_at) VALUES(?,?,?,?,?,?)",
        (current_user()["id"], name, idea, audience, "p" + hashlib.md5(f"{name}{time.time()}".encode()).hexdigest()[:8], db.now()))
    return redirect(url_for("workspace", pid=pid, run=1))


@app.route("/project/<int:pid>/delete", methods=["POST"])
def delete_project(pid):
    get_project(pid)
    for table in ("visits", "leads", "artifacts", "versions", "todos"):
        db.execute(f"DELETE FROM {table} WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    flash("项目已删除。", "ok")
    return redirect(url_for("home"))


@app.route("/project/<int:pid>")
def workspace(pid):
    p = get_project(pid)
    arts = db.q("SELECT * FROM artifacts WHERE project_id=? ORDER BY id", (pid,))
    versions = db.q("SELECT * FROM versions WHERE project_id=? ORDER BY id DESC", (pid,))
    cur = None
    if p["current_version_id"]:
        cur = db.q("SELECT * FROM versions WHERE id=?", (p["current_version_id"],), one=True)
    cfg = json.loads(p["config"]) if p["config"] else None
    questions = [] if cfg else gen.build_questions(p["idea"], p["audience"])
    stats = {
        "views": db.q("SELECT COUNT(*) c FROM visits WHERE project_id=?", (pid,), one=True)["c"],
        "uv": db.q("SELECT COUNT(DISTINCT ip_hash) c FROM visits WHERE project_id=?", (pid,), one=True)["c"],
        "leads": db.q("SELECT COUNT(*) c FROM leads WHERE project_id=?", (pid,), one=True)["c"],
    }
    daily = db.q("""SELECT date(ts,'unixepoch','localtime') d, COUNT(*) c
                    FROM visits WHERE project_id=? AND ts>?
                    GROUP BY d ORDER BY d""", (pid, db.now() - 7 * 86400))
    recent = db.q("SELECT * FROM visits WHERE project_id=? ORDER BY id DESC LIMIT 8", (pid,))
    leads = db.q("SELECT * FROM leads WHERE project_id=? ORDER BY id DESC LIMIT 20", (pid,))
    todos = db.q("SELECT * FROM todos WHERE project_id=? ORDER BY status, id DESC", (pid,))
    return render_template("project.html", p=p, arts=arts, versions=versions, cur=cur,
                           stats=stats, daily=daily, recent=recent, leads=leads, todos=todos,
                           config=cfg, questions=questions,
                           run=request.args.get("run"))


@app.route("/project/<int:pid>/configure", methods=["POST"])
def configure(pid):
    p = get_project(pid)
    if p["config"]:
        return redirect(url_for("workspace", pid=pid))
    styles = [s for s in request.form.getlist("styles") if s in ("neo", "mag")] or ["neo", "mag"]
    value = request.form.get("value", "time")
    if value not in gen.VALUE_SLOGAN:
        value = "time"
    sections = [s for s in request.form.getlist("sections")
                if s in ("pricing", "faq", "testimonials")]
    model = request.form.get("model", "sub")
    if model not in gen.PRICING_PLANS:
        model = "sub"
    cfg = {"styles": styles, "value": value, "sections": sections, "model": model}
    db.execute("UPDATE projects SET config=? WHERE id=?",
               (json.dumps(cfg, ensure_ascii=False), pid))
    return redirect(url_for("workspace", pid=pid, run=1))


@app.route("/project/<int:pid>/stats.json")
def stats_json(pid):
    get_project(pid)
    views = db.q("SELECT COUNT(*) c FROM visits WHERE project_id=?", (pid,), one=True)["c"]
    uv = db.q("SELECT COUNT(DISTINCT ip_hash) c FROM visits WHERE project_id=?", (pid,), one=True)["c"]
    leads = db.q("SELECT COUNT(*) c FROM leads WHERE project_id=?", (pid,), one=True)["c"]
    daily = db.q("""SELECT date(ts,'unixepoch','localtime') d, COUNT(*) c
                    FROM visits WHERE project_id=? AND ts>?
                    GROUP BY d ORDER BY d""", (pid, db.now() - 7 * 86400))
    return jsonify({"views": views, "uv": uv, "leads": leads,
                    "conv": round(leads / views * 100, 1) if views else 0,
                    "daily": [{"d": r["d"], "c": r["c"]} for r in daily]})


@app.route("/project/<int:pid>/stream")
def stream(pid):
    p = get_project(pid)

    def type_out(role, content, delay=0.03):
        for i in range(0, len(content), 60):
            yield sse("token", {"agent": role, "text": content[i:i + 60]})
            time.sleep(delay)

    def events():
        existing = db.q("SELECT COUNT(*) c FROM artifacts WHERE project_id=?", (pid,), one=True)["c"]
        if existing:
            yield sse("info", {"msg": "团队已完成构建，时间线见下方档案"})
            yield sse("done", {"phase": "built"})
            return

        cfg = json.loads(p["config"]) if p["config"] else None

        # -------- phase 1: clarify --------
        if not cfg:
            yield sse("info", {"msg": f"虚拟团队已就位，正在理解「{p['name']}」…"})
            yield sse("agent_start", {"agent": "Alex · 全栈工程师"})
            time.sleep(0.4)
            yield from type_out("Alex · 全栈工程师", "I'm getting started.")
            yield sse("agent_done", {"agent": "Alex · 全栈工程师", "title": "任务接入"})
            time.sleep(0.2)

            yield sse("agent_start", {"agent": "Emma · 产品经理"})
            time.sleep(0.4)
            yield from type_out("Emma · 产品经理",
                                gen.clarify_message(p["name"], p["idea"], p["audience"] or ""))
            yield sse("agent_done", {"agent": "Emma · 产品经理", "title": "需求澄清"})
            yield sse("questions", {"questions": gen.build_questions(p["idea"], p["audience"])})
            yield sse("done", {"phase": "clarify"})
            return

        # -------- phase 2: full build with user config --------
        yield sse("info", {"msg": f"配置已确认，虚拟团队开始为「{p['name']}」工作…"})
        for key, role, title, fn in AGENTS:
            yield sse("agent_start", {"agent": role})
            time.sleep(0.4)
            t, content = fn(p["name"], p["idea"], p["audience"] or "早期种子用户")
            yield from type_out(role, content)
            db.execute("INSERT INTO artifacts(project_id,agent,title,content,created_at) VALUES(?,?,?,?,?)",
                       (pid, role, t, content, db.now()))
            yield sse("agent_done", {"agent": role, "title": t})
            time.sleep(0.2)
        # Alex: race mode - variants follow user's style choices
        labels = {"neo": "深色科技风", "mag": "浅色杂志风"}
        styles = (cfg.get("styles") or ["neo", "mag"])[:2]
        variants = [(chr(65 + i), s, labels[s]) for i, s in enumerate(styles)]
        yield sse("agent_start", {"agent": "Alex · 全栈工程师（Race Mode）"})
        time.sleep(0.5)
        first_vid = None
        for variant, style, note in variants:
            spec = gen.base_spec(p["name"], p["idea"], p["audience"] or "早期种子用户", style, cfg)
            spec["v"] = 1
            vid = db.execute(
                "INSERT INTO versions(project_id,variant,spec,note,created_at) VALUES(?,?,?,?,?)",
                (pid, variant, json.dumps(spec, ensure_ascii=False), f"Race 方案 {variant} · {note}", db.now()))
            first_vid = first_vid or vid
            yield sse("token", {"agent": "Alex · 全栈工程师（Race Mode）",
                                "text": f"\n✅ 方案 {variant}（{note}）构建完成"})
            time.sleep(0.3)
        # 只选了一个风格时直接采纳，跳过选择步骤
        if len(variants) == 1:
            db.execute("UPDATE projects SET current_version_id=? WHERE id=?", (first_vid, pid))
        yield sse("agent_done", {"agent": "Alex · 全栈工程师（Race Mode）", "title": "落地页双方案"})
        yield sse("done", {"phase": "built",
                           "msg": "全部产出完成！请在下方选择赛马方案并发布。"})

    return Response(events(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/project/<int:pid>/choose/<int:vid>", methods=["POST"])
def choose(pid, vid):
    get_project(pid)
    v = db.q("SELECT * FROM versions WHERE id=? AND project_id=?", (vid, pid), one=True)
    if not v:
        abort(404)
    db.execute("UPDATE projects SET current_version_id=? WHERE id=?", (vid, pid))
    return redirect(url_for("workspace", pid=pid) + "#iterate")


@app.route("/project/<int:pid>/iterate", methods=["POST"])
def iterate(pid):
    p = get_project(pid)
    cmd = request.form.get("cmd", "").strip()
    if not cmd or not p["current_version_id"]:
        return redirect(url_for("workspace", pid=pid) + "#iterate")
    cur = db.q("SELECT * FROM versions WHERE id=?", (p["current_version_id"],), one=True)
    spec = json.loads(cur["spec"])
    new_spec, reply, applied = gen.apply_command(spec, cmd)
    if not applied:
        db.execute("INSERT INTO todos(project_id,text,status,created_at) VALUES(?,?,?,?)",
                   (pid, cmd[:200], "open", db.now()))
        flash(reply, "err")
        return redirect(url_for("workspace", pid=pid) + "#iterate")
    new_spec["v"] = int(new_spec.get("v", 1)) + 1
    vid = db.execute("INSERT INTO versions(project_id,variant,spec,note,created_at) VALUES(?,?,?,?,?)",
                     (pid, "iter", json.dumps(new_spec, ensure_ascii=False),
                      f"指令：{cmd[:60]} → {reply[:60]}", db.now()))
    db.execute("UPDATE projects SET current_version_id=? WHERE id=?", (vid, pid))
    return redirect(url_for("workspace", pid=pid) + "#iterate")


@app.route("/project/<int:pid>/todo/<int:tid>/done", methods=["POST"])
def todo_done(pid, tid):
    get_project(pid)
    db.execute("UPDATE todos SET status='done' WHERE id=? AND project_id=?", (tid, pid))
    return redirect(url_for("workspace", pid=pid) + "#todos")


@app.route("/project/<int:pid>/todo/<int:tid>/drop", methods=["POST"])
def todo_drop(pid, tid):
    get_project(pid)
    db.execute("DELETE FROM todos WHERE id=? AND project_id=?", (tid, pid))
    return redirect(url_for("workspace", pid=pid) + "#todos")


@app.route("/project/<int:pid>/publish", methods=["POST"])
def publish(pid):
    p = get_project(pid)
    if p["current_version_id"]:
        db.execute("UPDATE projects SET published=1 WHERE id=?", (pid,))
    return redirect(url_for("workspace", pid=pid) + "#publish")


@app.route("/project/<int:pid>/unpublish", methods=["POST"])
def unpublish(pid):
    get_project(pid)
    db.execute("UPDATE projects SET published=0 WHERE id=?", (pid,))
    return redirect(url_for("workspace", pid=pid))


@app.route("/project/<int:pid>/preview/<int:vid>")
def preview(pid, vid):
    get_project(pid)
    v = db.q("SELECT * FROM versions WHERE id=? AND project_id=?", (vid, pid), one=True)
    if not v:
        abort(404)
    return gen.render_page(json.loads(v["spec"]), "preview")


# ------------------------------------------------------------- public pages

def is_bot():
    ua = (request.headers.get("User-Agent", "") or "").lower()
    return any(b in ua for b in BOT_UA)


@app.route("/p/<slug>")
def public_page(slug):
    p = db.q("SELECT * FROM projects WHERE slug=? AND published=1", (slug,), one=True)
    if not p:
        abort(404)
    if not is_bot():
        db.execute("INSERT INTO visits(project_id,ts,ip_hash,ua,ref) VALUES(?,?,?,?,?)",
                   (p["id"], db.now(), ip_hash(request.remote_addr),
                    request.headers.get("User-Agent", "")[:200],
                    request.headers.get("Referer", "")[:200]))
    v = db.q("SELECT * FROM versions WHERE id=?", (p["current_version_id"],), one=True)
    return gen.render_page(json.loads(v["spec"]), slug, request.args.get("msg", ""))


@app.route("/p/<slug>/subscribe", methods=["POST"])
def subscribe(slug):
    p = db.q("SELECT * FROM projects WHERE slug=? AND published=1", (slug,), one=True)
    if not p:
        abort(404)
    # 蜜罐：真人不可见，机器人填了直接静默丢弃
    if request.form.get("website"):
        return redirect(f"/p/{slug}?msg=" + "🎉 订阅成功！内测开通后将第一时间通知你")
    email = request.form.get("email", "").strip()[:120]
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        dup = db.q("SELECT id FROM leads WHERE project_id=? AND email=?", (p["id"], email), one=True)
        if not dup:
            db.execute("INSERT INTO leads(project_id,email,ts) VALUES(?,?,?)", (p["id"], email, db.now()))
        return redirect(f"/p/{slug}?msg=" + "🎉 订阅成功！内测开通后将第一时间通知你")
    return redirect(f"/p/{slug}?msg=邮箱格式不正确，请重试")


if __name__ == "__main__":
    db.init_db()
    app.run(host="127.0.0.1", port=5050, threaded=True)
