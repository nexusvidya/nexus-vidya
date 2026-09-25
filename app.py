#!/usr/bin/env python3
"""Nexus Vidya CMS"""
import os, re, sqlite3, uuid
from datetime import datetime
from functools import wraps
import html as html_module
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup, escape
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nexus-vidya-secret-key-2026")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "instance", "vedic.db")
ALLOWED_IMAGE = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
ALLOWED_VIDEO = {"mp4", "webm", "mov", "avi", "mkv"}
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

TRANSLATIONS = {
    "hi": {"site_name": "Nexus Vidya", "tagline": "ज्ञान का केंद्र", "home": "होम", "search_placeholder": "खोजें...", "admin": "एडमिन", "latest_posts": "नवीनतम लेख", "main_topics": "मुख्य विषय", "read_more": "और पढ़ें", "categories": "विषय", "links": "लिंक", "footer_text": "ज्ञान का केंद्र", "all_rights": "सभी अधिकार सुरक्षित", "no_posts": "अभी कोई लेख नहीं", "related": "संबंधित लेख", "views": "बार पढ़ा गया", "search_results": "खोज परिणाम", "no_results": "कोई परिणाम नहीं", "login": "लॉगिन", "username": "यूजरनेम", "password": "पासवर्ड", "welcome": "स्वागत है!", "subcategories": "उप-श्रेणियाँ", "articles": "लेख", "media_gallery": "मीडिया"},
    "en": {"site_name": "Nexus Vidya", "tagline": "Centre of Knowledge", "home": "Home", "search_placeholder": "Search...", "admin": "Admin", "latest_posts": "Latest Articles", "main_topics": "Main Topics", "read_more": "Read more", "categories": "Topics", "links": "Links", "footer_text": "Centre of Knowledge", "all_rights": "All rights reserved", "no_posts": "No articles yet", "related": "Related", "views": "views", "search_results": "Search Results", "no_results": "No results", "login": "Login", "username": "Username", "password": "Password", "welcome": "Welcome!", "subcategories": "Sub-categories", "articles": "Articles", "media_gallery": "Media"},
}

def get_lang():
    lang = session.get("lang") or request.args.get("lang") or "hi"
    return lang if lang in TRANSLATIONS else "hi"

def t(key):
    return TRANSLATIONS.get(get_lang(), TRANSLATIONS["hi"]).get(key, key)

@app.context_processor
def inject_globals():
    nav_categories, nav_children = [], {}
    try:
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        all_cats = conn.execute("SELECT id, name, slug, icon, parent_id, is_active FROM categories WHERE (is_active = 1 OR is_active IS NULL) ORDER BY sort_order, name").fetchall()
        conn.close()
        for c in all_cats:
            if c["parent_id"] in (None, 0):
                nav_categories.append(c)
            else:
                nav_children.setdefault(c["parent_id"], []).append(c)
    except Exception:
        nav_categories, nav_children = [], {}
    return {"t": t, "current_lang": get_lang(), "site_name": "Nexus Vidya", "nav_categories": nav_categories, "nav_children": nav_children}

@app.route("/set-lang/<lang>")
def set_lang(lang):
    if lang in TRANSLATIONS:
        session["lang"] = lang
    return redirect(request.referrer or url_for("index"))

def _md_inline(s):
    s = escape(s)
    s = s.replace("\\circ", "°").replace("^\\circ", "°")
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", s)
    return s

@app.template_filter("format_content")
def format_content_filter(text):
    if not text:
        return ""
    text = str(text).strip()
    if "<" in text or ">" in text:
        text = html_module.unescape(text)
    lower = text.lower()
    if any(tag in lower for tag in ("<p>", "<p ", "<br", "<h1", "<h2", "<h3", "<ul", "<ol")):
        return Markup(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+(?=#{1,3}\s)", "\n\n", text)
    text = re.sub(r"\s+(?=---\s*)", "\n\n", text)
    parts = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        first = lines[0]
        if first.strip("-") == "" or first == "---":
            parts.append("<hr>"); continue
        m = re.match(r"^(#{1,3})\s+(.+)$", first)
        if m:
            level = min(len(m.group(1)) + 1, 4)
            parts.append(f"<h{level}>" + _md_inline(m.group(2)) + f"</h{level}>")
            if lines[1:]:
                parts.append("<p>" + "<br>\n".join(_md_inline(x) for x in lines[1:]) + "</p>")
            continue
        if re.match(r"^[\-\u2022]\s+", first) or (first.startswith("* ") and not first.startswith("**")):
            items = ["<li>" + _md_inline(re.sub(r"^[\*\-\u2022]\s+", "", ln)) + "</li>" for ln in lines]
            parts.append("<ul>" + "".join(items) + "</ul>"); continue
        parts.append("<p>" + "<br>\n".join(_md_inline(x) for x in lines) + "</p>")
    return Markup("\n".join(parts))

def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, full_name TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, description TEXT, icon TEXT DEFAULT '📚', parent_id INTEGER DEFAULT NULL, sort_order INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (parent_id) REFERENCES categories(id) ON DELETE SET NULL);
    CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, content TEXT, excerpt TEXT, category_id INTEGER, featured_image TEXT, status TEXT DEFAULT 'published', views INTEGER DEFAULT 0, author_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL, FOREIGN KEY (author_id) REFERENCES users(id) ON DELETE SET NULL);
    CREATE TABLE IF NOT EXISTS media (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, filename TEXT NOT NULL, original_name TEXT, media_type TEXT NOT NULL, file_size INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (post_id) REFERENCES posts(id) ON DELETE CASCADE);
    """)
    cur.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (username, password_hash, full_name) VALUES (?, ?, ?)", ("admin", generate_password_hash("admin123"), "Admin"))
    defaults = [("ज्योतिष", "jyotish", "वैदिक ज्योतिष", "🔮", None), ("वास्तु शास्त्र", "vastu", "वास्तु", "🏠", None), ("वैदिक न्यूरोलॉजी", "vedic-neurology", "वैदिक विज्ञान", "🧠", None), ("नेम न्यूमेरोलॉजी", "name-numerology", "नाम अंक", "🔢", None), ("करंट अफेयर्स", "current-affairs", "समसामयिक", "📰", None)]
    for name, slug, desc, icon, parent in defaults:
        cur.execute("SELECT id FROM categories WHERE slug = ?", (slug,))
        if not cur.fetchone():
            cur.execute("INSERT INTO categories (name, slug, description, icon, parent_id) VALUES (?, ?, ?, ?, ?)", (name, slug, desc, icon, parent))
    conn.commit(); conn.close()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("कृपया पहले लॉगिन करें", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_-]+", "-", text).strip("-")
    return (text or str(uuid.uuid4())[:8])[:80]

def allowed_file(filename, media_type="image"):
    if "." not in filename: return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_IMAGE if media_type == "image" else ext in ALLOWED_VIDEO

def save_upload(file, media_type="image"):
    if not file or file.filename == "" or not allowed_file(file.filename, media_type):
        return None
    ext = file.filename.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], new_name))
    return new_name

@app.route("/")
def index():
    conn = get_db()
    categories = conn.execute("SELECT * FROM categories WHERE parent_id IS NULL AND is_active = 1 ORDER BY sort_order, name").fetchall()
    latest_posts = conn.execute("SELECT p.*, c.name as category_name, c.icon as category_icon, c.slug as category_slug FROM posts p LEFT JOIN categories c ON p.category_id = c.id WHERE p.status = 'published' ORDER BY p.created_at DESC LIMIT 12").fetchall()
    conn.close()
    return render_template("index.html", categories=categories, posts=latest_posts)

@app.route("/category/<slug>")
def category_page(slug):
    conn = get_db()
    category = conn.execute("SELECT * FROM categories WHERE slug = ? AND is_active = 1", (slug,)).fetchone()
    if not category:
        conn.close(); abort(404)
    subcategories = conn.execute("SELECT * FROM categories WHERE parent_id = ? AND is_active = 1 ORDER BY sort_order, name", (category["id"],)).fetchall()
    posts = list(conn.execute("SELECT p.*, c.name as category_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id WHERE p.category_id = ? AND p.status = 'published' ORDER BY p.created_at DESC", (category["id"],)).fetchall())
    if subcategories:
        sub_ids = [s["id"] for s in subcategories]
        ph = ",".join("?" * len(sub_ids))
        posts += list(conn.execute(f"SELECT p.*, c.name as category_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id WHERE p.category_id IN ({ph}) AND p.status = 'published' ORDER BY p.created_at DESC", sub_ids).fetchall())
    conn.close()
    return render_template("category.html", category=category, subcategories=subcategories, posts=posts)

@app.route("/post/<slug>")
def post_page(slug):
    conn = get_db()
    post = conn.execute("SELECT p.*, c.name as category_name, c.slug as category_slug, c.icon as category_icon, u.full_name as author_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id LEFT JOIN users u ON p.author_id = u.id WHERE p.slug = ? AND p.status = 'published'", (slug,)).fetchone()
    if not post:
        conn.close(); abort(404)
    conn.execute("UPDATE posts SET views = views + 1 WHERE id = ?", (post["id"],)); conn.commit()
    media = conn.execute("SELECT * FROM media WHERE post_id = ? ORDER BY id", (post["id"],)).fetchall()
    related = conn.execute("SELECT p.*, c.name as category_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id WHERE p.category_id = ? AND p.id != ? AND p.status = 'published' ORDER BY p.created_at DESC LIMIT 4", (post["category_id"], post["id"])).fetchall()
    conn.close()
    return render_template("post.html", post=post, media=media, related=related)

@app.route("/search")
def search():
    q = request.args.get("q", "").strip(); posts = []
    if q:
        conn = get_db()
        posts = conn.execute("SELECT p.*, c.name as category_name, c.icon as category_icon FROM posts p LEFT JOIN categories c ON p.category_id = c.id WHERE p.status = 'published' AND (p.title LIKE ? OR p.content LIKE ? OR p.excerpt LIKE ?) ORDER BY p.created_at DESC LIMIT 30", (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()
        conn.close()
    return render_template("search.html", posts=posts, query=q)

@app.route("/contact")
@app.route("/samsparsh")
def contact_page():
    return render_template("contact.html")

@app.route("/robots.txt")
def robots_txt():
    return "User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: https://nexus-vidya.onrender.com/sitemap.xml\n", 200, {"Content-Type": "text/plain; charset=utf-8"}

@app.route("/sitemap.xml")
def sitemap_xml():
    conn = get_db()
    posts = conn.execute("SELECT slug FROM posts WHERE status = 'published'").fetchall()
    cats = conn.execute("SELECT slug FROM categories WHERE is_active = 1 OR is_active IS NULL").fetchall()
    conn.close()
    base = "https://nexus-vidya.onrender.com"
    urls = [f"{base}/", f"{base}/contact"] + [f"{base}/category/{c['slug']}" for c in cats] + [f"{base}/post/{p['slug']}" for p in posts]
    items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    return '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + items + "</urlset>", 200, {"Content-Type": "application/xml; charset=utf-8"}

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]; session["username"] = user["username"]; session["full_name"] = user["full_name"]
            flash("लॉगिन सफल", "success")
            return redirect(url_for("admin_dashboard"))
        flash("गलत यूजरनेम या पासवर्ड", "danger")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear(); flash("लॉगआउट", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin/change-password", methods=["GET", "POST"])
@login_required
def admin_change_password():
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_username = request.form.get("new_username", "").strip()
        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not user or not check_password_hash(user["password_hash"], current):
            conn.close(); flash("वर्तमान पासवर्ड गलत", "danger")
            return render_template("admin/change_password.html")
        if new_password and len(new_password) < 6:
            conn.close(); flash("पासवर्ड कम से कम 6 अक्षर", "danger")
            return render_template("admin/change_password.html")
        if new_password and new_password != confirm:
            conn.close(); flash("पासवर्ड मेल नहीं", "danger")
            return render_template("admin/change_password.html")
        if new_username and new_username != user["username"]:
            exists = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (new_username, user["id"])).fetchone()
            if exists:
                conn.close(); flash("यूजरनेम पहले से है", "danger")
                return render_template("admin/change_password.html")
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, user["id"]))
            session["username"] = new_username
        if new_password:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new_password), user["id"]))
        conn.commit(); conn.close(); flash("अपडेट हो गया", "success")
        if new_password or (new_username and new_username != user["username"]):
            session.clear(); return redirect(url_for("admin_login"))
        return redirect(url_for("admin_dashboard"))
    return render_template("admin/change_password.html")

@app.route("/admin")
@login_required
def admin_dashboard():
    conn = get_db()
    stats = {"posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0], "categories": conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0], "media": conn.execute("SELECT COUNT(*) FROM media").fetchone()[0], "views": conn.execute("SELECT COALESCE(SUM(views),0) FROM posts").fetchone()[0]}
    recent = conn.execute("SELECT p.*, c.name as category_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.created_at DESC LIMIT 8").fetchall()
    conn.close()
    return render_template("admin/dashboard.html", stats=stats, recent=recent)

@app.route("/admin/categories")
@login_required
def admin_categories():
    conn = get_db()
    cats = conn.execute("SELECT c.*, p.name as parent_name, (SELECT COUNT(*) FROM posts WHERE category_id = c.id) as post_count FROM categories c LEFT JOIN categories p ON c.parent_id = p.id ORDER BY c.parent_id IS NOT NULL, c.sort_order, c.name").fetchall()
    parents = conn.execute("SELECT id, name FROM categories WHERE parent_id IS NULL ORDER BY name").fetchall()
    conn.close()
    return render_template("admin/categories.html", categories=cats, parents=parents)

@app.route("/admin/categories/add", methods=["POST"])
@login_required
def admin_category_add():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "📚").strip() or "📚"
    parent_id = request.form.get("parent_id") or None
    if parent_id: parent_id = int(parent_id)
    if not name:
        flash("नाम जरूरी", "danger"); return redirect(url_for("admin_categories"))
    slug = slugify(name); conn = get_db(); base = slug; i = 1
    while conn.execute("SELECT id FROM categories WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{i}"; i += 1
    conn.execute("INSERT INTO categories (name, slug, description, icon, parent_id) VALUES (?, ?, ?, ?, ?)", (name, slug, description, icon, parent_id))
    conn.commit(); conn.close(); flash("कैटेगरी बनी", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/edit/<int:id>", methods=["POST"])
@login_required
def admin_category_edit(id):
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "📚").strip() or "📚"
    parent_id = request.form.get("parent_id") or None
    is_active = 1 if request.form.get("is_active") else 0
    if parent_id:
        parent_id = int(parent_id)
        if parent_id == id: parent_id = None
    if not name:
        flash("नाम जरूरी", "danger"); return redirect(url_for("admin_categories"))
    conn = get_db()
    conn.execute("UPDATE categories SET name=?, description=?, icon=?, parent_id=?, is_active=? WHERE id=?", (name, description, icon, parent_id, is_active, id))
    conn.commit(); conn.close(); flash("अपडेट", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/categories/delete/<int:id>", methods=["POST"])
@login_required
def admin_category_delete(id):
    conn = get_db(); conn.execute("DELETE FROM categories WHERE id = ?", (id,)); conn.commit(); conn.close()
    flash("हटाई", "info"); return redirect(url_for("admin_categories"))

@app.route("/admin/posts")
@login_required
def admin_posts():
    conn = get_db()
    posts = conn.execute("SELECT p.*, c.name as category_name FROM posts p LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.created_at DESC").fetchall()
    conn.close()
    return render_template("admin/posts.html", posts=posts)

@app.route("/admin/posts/new", methods=["GET", "POST"])
@login_required
def admin_post_new():
    conn = get_db()
    categories = conn.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY parent_id IS NOT NULL, name").fetchall()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "")
        excerpt = request.form.get("excerpt", "").strip()
        category_id = request.form.get("category_id") or None
        status = request.form.get("status", "published")
        if not title:
            conn.close(); flash("शीर्षक जरूरी", "danger")
            return render_template("admin/post_form.html", categories=categories, post=None)
        slug = slugify(title); base = slug; i = 1
        while conn.execute("SELECT id FROM posts WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base}-{i}"; i += 1
        featured = None
        if "featured_image" in request.files:
            f = request.files["featured_image"]
            if f and f.filename: featured = save_upload(f, "image")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute("INSERT INTO posts (title, slug, content, excerpt, category_id, featured_image, status, author_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (title, slug, content, excerpt, category_id, featured, status, session["user_id"], now, now))
        post_id = cur.lastrowid
        if "media_files" in request.files:
            for f in request.files.getlist("media_files"):
                if f and f.filename:
                    is_video = allowed_file(f.filename, "video"); is_image = allowed_file(f.filename, "image")
                    if is_video or is_image:
                        mtype = "video" if is_video else "image"
                        fname = save_upload(f, mtype)
                        if fname:
                            size = os.path.getsize(os.path.join(app.config["UPLOAD_FOLDER"], fname))
                            conn.execute("INSERT INTO media (post_id, filename, original_name, media_type, file_size) VALUES (?, ?, ?, ?, ?)", (post_id, fname, f.filename, mtype, size))
        conn.commit(); conn.close(); flash("पोस्ट बनी", "success")
        return redirect(url_for("admin_posts"))
    conn.close()
    return render_template("admin/post_form.html", categories=categories, post=None)

@app.route("/admin/posts/edit/<int:id>", methods=["GET", "POST"])
@login_required
def admin_post_edit(id):
    conn = get_db()
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (id,)).fetchone()
    if not post:
        conn.close(); abort(404)
    categories = conn.execute("SELECT * FROM categories WHERE is_active = 1 ORDER BY parent_id IS NOT NULL, name").fetchall()
    media = conn.execute("SELECT * FROM media WHERE post_id = ?", (id,)).fetchall()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "")
        excerpt = request.form.get("excerpt", "").strip()
        category_id = request.form.get("category_id") or None
        status = request.form.get("status", "published")
        if not title:
            conn.close(); flash("शीर्षक जरूरी", "danger")
            return render_template("admin/post_form.html", categories=categories, post=post, media=media)
        featured = post["featured_image"]
        if "featured_image" in request.files:
            f = request.files["featured_image"]
            if f and f.filename:
                nf = save_upload(f, "image")
                if nf: featured = nf
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("UPDATE posts SET title=?, content=?, excerpt=?, category_id=?, featured_image=?, status=?, updated_at=? WHERE id=?", (title, content, excerpt, category_id, featured, status, now, id))
        if "media_files" in request.files:
            for f in request.files.getlist("media_files"):
                if f and f.filename:
                    is_video = allowed_file(f.filename, "video"); is_image = allowed_file(f.filename, "image")
                    if is_video or is_image:
                        mtype = "video" if is_video else "image"
                        fname = save_upload(f, mtype)
                        if fname:
                            size = os.path.getsize(os.path.join(app.config["UPLOAD_FOLDER"], fname))
                            conn.execute("INSERT INTO media (post_id, filename, original_name, media_type, file_size) VALUES (?, ?, ?, ?, ?)", (id, fname, f.filename, mtype, size))
        conn.commit(); conn.close(); flash("अपडेट", "success")
        return redirect(url_for("admin_posts"))
    conn.close()
    return render_template("admin/post_form.html", categories=categories, post=post, media=media)

@app.route("/admin/posts/delete/<int:id>", methods=["POST"])
@login_required
def admin_post_delete(id):
    conn = get_db(); conn.execute("DELETE FROM posts WHERE id = ?", (id,)); conn.commit(); conn.close()
    flash("पोस्ट हटाई", "info"); return redirect(url_for("admin_posts"))

@app.route("/admin/media/delete/<int:id>", methods=["POST"])
@login_required
def admin_media_delete(id):
    conn = get_db()
    media = conn.execute("SELECT * FROM media WHERE id = ?", (id,)).fetchone()
    if media:
        try: os.remove(os.path.join(app.config["UPLOAD_FOLDER"], media["filename"]))
        except OSError: pass
        conn.execute("DELETE FROM media WHERE id = ?", (id,)); conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("admin_posts"))

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(413)
def too_large(e):
    flash("फाइल बहुत बड़ी", "danger")
    return redirect(request.referrer or url_for("admin_dashboard"))

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
