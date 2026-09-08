from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, Response, session, g
from datetime import datetime, timedelta
from authlib.integrations.flask_client import OAuth
import csv
import io
import os
import sys
import secrets
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import FoodDatabase
from analyzer import FoodAnalyzer

app = Flask(__name__,
            template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates'),
            static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static'))

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", secrets.token_hex(32)),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
)

oauth = OAuth(app)

oauth.register(
    name='google',
    client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
    client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

oauth.register(
    name='github',
    client_id=os.environ.get("GITHUB_CLIENT_ID", ""),
    client_secret=os.environ.get("GITHUB_CLIENT_SECRET"),
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    api_base_url='https://api.github.com/',
    client_kwargs={'scope': 'user:email'},
)

oauth.register(
    name='apple',
    client_id=os.environ.get("APPLE_CLIENT_ID", ""),
    client_secret=os.environ.get("APPLE_CLIENT_SECRET", ""),
    access_token_url='https://appleid.apple.com/auth/token',
    access_token_params=None,
    authorize_url='https://appleid.apple.com/auth/authorize',
    authorize_params=None,
    api_base_url='https://appleid.apple.com/',
    client_kwargs={'scope': 'name email'},
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

db = FoodDatabase(":memory:")
analyzer = FoodAnalyzer(db)


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("signin"))
        return f(*args, **kwargs)
    return decorated_function


def get_user_id():
    return session.get("user_id")


@app.after_request
def after_request(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


@app.context_processor
def inject_globals():
    user_id = get_user_id()
    expiring_count = 0
    user = None
    try:
        expiring_count = len(db.get_expiring_items(3, user_id))
        if user_id:
            user = db.get_user_by_id(user_id)
    except Exception as e:
        logger.error(f"inject_globals error: {e}")
    return {"expiring_count": expiring_count, "user": user}


@app.errorhandler(404)
def page_not_found(e):
    return render_template("error.html", code=404, message="Page not found"), 404


@app.errorhandler(500)
def internal_error(e):
    return render_template("error.html", code=500, message="Something went wrong"), 500


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for("user_dashboard"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not all([username, email, password]):
            flash("Please fill in all required fields.", "error")
            return render_template("signup.html")
        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
            return render_template("signup.html")
        if '@' not in email or '.' not in email:
            flash("Please enter a valid email address.", "error")
            return render_template("signup.html")
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup.html")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup.html")
        result = db.create_user(username, email, password, full_name)
        if result["success"]:
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("signin"))
        else:
            flash(result["message"], "error")
    return render_template("signup.html")


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if "user_id" in session:
        return redirect(url_for("user_dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Please enter username and password.", "error")
            return render_template("signin.html")
        result = db.authenticate_user(username, password)
        if result["success"]:
            session.permanent = True
            session["user_id"] = result["user"]["id"]
            session["username"] = result["user"]["username"]
            flash(f"Welcome back, {result['user']['username']}!", "success")
            return redirect(url_for("user_dashboard"))
        else:
            flash(result["message"], "error")
    return render_template("signin.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("signin"))


# ==================== OAUTH ROUTES ====================

@app.route("/auth/<provider>")
def oauth_login(provider):
    if provider not in ('google', 'github', 'apple'):
        flash("Invalid provider.", "error")
        return redirect(url_for("signin"))
    
    client = oauth.create_client(provider)
    if not client:
        flash(f"{provider.title()} login is not configured.", "error")
        return redirect(url_for("signin"))
    
    redirect_uri = url_for("oauth_callback", provider=provider, _external=True)
    return client.authorize_redirect(redirect_uri)


@app.route("/auth/<provider>/callback")
def oauth_callback(provider):
    if provider not in ('google', 'github', 'apple'):
        flash("Invalid provider.", "error")
        return redirect(url_for("signin"))
    
    client = oauth.create_client(provider)
    if not client:
        flash(f"{provider.title()} login is not configured.", "error")
        return redirect(url_for("signin"))
    
    try:
        token = client.authorize_access_token()
        
        if provider == 'google':
            resp = client.get('userinfo')
            resp.raise_for_status()
            user_info = resp.json()
            email = user_info.get('email', '')
            name = user_info.get('name', '')
            provider_id = user_info.get('sub', user_info.get('id', ''))
        
        elif provider == 'github':
            resp = client.get('user')
            resp.raise_for_status()
            user_info = resp.json()
            email = user_info.get('email', '')
            name = user_info.get('name', '') or user_info.get('login', '')
            provider_id = str(user_info.get('id', ''))
            
            if not email:
                emails_resp = client.get('user/emails')
                emails_resp.raise_for_status()
                emails = emails_resp.json()
                for e in emails:
                    if e.get('primary'):
                        email = e['email']
                        break
                if not email and emails:
                    email = emails[0]['email']
        
        elif provider == 'apple':
            user_info = client.parse_id_token(token)
            email = user_info.get('email', '')
            name = user_info.get('name', {}).get('firstName', '') + ' ' + user_info.get('name', {}).get('lastName', '')
            name = name.strip() or email.split('@')[0]
            provider_id = user_info.get('sub', '')
        
        if not email or not provider_id:
            flash("Could not get your email from this provider.", "error")
            return redirect(url_for("signin"))
        
        result = db.get_or_create_oauth_user(provider, provider_id, email, name)
        
        if result["success"]:
            session.permanent = True
            session["user_id"] = result["user"]["id"]
            session["username"] = result["user"]["username"]
            flash(f"Welcome, {result['user']['username']}!", "success")
            return redirect(url_for("user_dashboard"))
        else:
            flash(result["message"], "error")
            return redirect(url_for("signin"))
    
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        flash(f"Authentication failed: {str(e)}", "error")
        return redirect(url_for("signin"))


@app.route("/dashboard")
@login_required
def user_dashboard():
    user_id = get_user_id()
    try:
        user = db.get_user_by_id(user_id)
        user_stats = db.get_user_stats(user_id)
        expiring_items = db.get_expiring_items(3, user_id)
        shopping_items = db.get_shopping_items(user_id)
        today = datetime.now().date()
        for item in expiring_items:
            item["days_left"] = (datetime.strptime(item["expiry_date"], "%Y-%m-%d").date() - today).days
        return render_template("user_dashboard.html",
                              user=user, user_stats=user_stats,
                              expiring_items=expiring_items,
                              shopping_items=shopping_items)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash("An error occurred.", "error")
        return redirect(url_for("dashboard"))


@app.route("/update-profile", methods=["POST"])
@login_required
def update_profile():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    if not email or '@' not in email:
        flash("Please enter a valid email.", "error")
        return redirect(url_for("user_dashboard"))
    if db.update_user_profile(session["user_id"], full_name, email):
        flash("Profile updated!", "success")
    else:
        flash("Email already in use.", "error")
    return redirect(url_for("user_dashboard"))


@app.route("/change-password", methods=["POST"])
@login_required
def change_password():
    old_password = request.form.get("old_password", "")
    new_password = request.form.get("new_password", "")
    if not old_password or not new_password:
        flash("Please fill in both fields.", "error")
        return redirect(url_for("user_dashboard"))
    if len(new_password) < 6:
        flash("New password must be at least 6 characters.", "error")
        return redirect(url_for("user_dashboard"))
    result = db.change_password(session["user_id"], old_password, new_password)
    if result["success"]:
        flash("Password changed!", "success")
    else:
        flash(result["message"], "error")
    return redirect(url_for("user_dashboard"))


@app.route("/")
@login_required
def dashboard():
    user_id = get_user_id()
    try:
        items = db.get_all_items(user_id)
        expiring = db.get_expiring_items(3, user_id)
        today = datetime.now().date()
        expired, fresh = [], []
        for i in items:
            days_left = (datetime.strptime(i["expiry_date"], "%Y-%m-%d").date() - today).days
            i["days_left"] = days_left
            status, badge, _ = analyzer.get_expiry_status(i["expiry_date"])
            i["status"], i["badge"] = status, badge
            if days_left < 0: expired.append(i)
            elif days_left >= 5: fresh.append(i)
        for i in expiring:
            i["days_left"] = (datetime.strptime(i["expiry_date"], "%Y-%m-%d").date() - today).days
            status, badge, _ = analyzer.get_expiry_status(i["expiry_date"])
            i["status"], i["badge"] = status, badge
        score = analyzer.calculate_waste_reduction_score(user_id)
        stats = db.get_waste_stats(30, user_id)
        return render_template("dashboard.html", items=items, expiring=expiring, expired=expired,
                               fresh=fresh, score=score, stats=stats, total_items=len(items))
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return render_template("dashboard.html", items=[], expiring=[], expired=[], fresh=[],
                               score={"score": 0, "message": "Error", "grade": "N/A"},
                               stats={"total_items_wasted": 0, "total_cost_lost": 0}, total_items=0)


@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    categories = db.get_categories()
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            category = request.form["category"]
            purchase_date = request.form["purchase_date"]
            expiry_date = request.form["expiry_date"]
            try: quantity = float(request.form.get("quantity", 1))
            except: quantity = 1
            unit = request.form.get("unit", "pcs")
            storage = request.form.get("storage", "fridge")
            notes = request.form.get("notes", "").strip()
            if not name or not expiry_date:
                flash("Name and expiry date are required!", "error")
                return redirect(url_for("add_item"))
            db.add_item(name, category, purchase_date, expiry_date, quantity, unit, storage, notes, get_user_id())
            flash(f"Added {name}!", "success")
            return redirect(url_for("dashboard"))
        except Exception as e:
            logger.error(f"Add item error: {e}")
            flash("An error occurred.", "error")
            return redirect(url_for("add_item"))
    return render_template("add.html", categories=categories, today=datetime.now().date().isoformat())


@app.route("/items")
@login_required
def view_items():
    user_id = get_user_id()
    try:
        items = db.get_all_items(user_id)
        today = datetime.now().date()
        for item in items:
            item["days_left"] = (datetime.strptime(item["expiry_date"], "%Y-%m-%d").date() - today).days
            status, badge, _ = analyzer.get_expiry_status(item["expiry_date"])
            item["status"], item["badge"] = status, badge
        return render_template("items.html", items=items)
    except Exception as e:
        logger.error(f"View items error: {e}")
        return render_template("items.html", items=[])


@app.route("/edit/<int:item_id>", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    user_id = get_user_id()
    categories = db.get_categories()
    if request.method == "POST":
        try:
            name = request.form["name"].strip()
            category = request.form["category"]
            purchase_date = request.form["purchase_date"]
            expiry_date = request.form["expiry_date"]
            try: quantity = float(request.form.get("quantity", 1))
            except: quantity = 1
            unit = request.form.get("unit", "pcs")
            storage = request.form.get("storage", "fridge")
            notes = request.form.get("notes", "").strip()
            if db.update_item(item_id, name, category, purchase_date, expiry_date, quantity, unit, storage, notes, user_id):
                flash("Item updated!", "success")
            else:
                flash("Item not found.", "error")
            return redirect(url_for("view_items"))
        except Exception as e:
            logger.error(f"Edit error: {e}")
            flash("An error occurred.", "error")
            return redirect(url_for("view_items"))
    item = db.get_item_by_id(item_id, user_id)
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("view_items"))
    return render_template("edit.html", item=item, categories=categories)


@app.route("/consume/<int:item_id>", methods=["POST"])
@login_required
def consume_item(item_id):
    try: db.mark_consumed(item_id, get_user_id()); flash("Consumed!", "success")
    except: flash("Error.", "error")
    return redirect(request.referrer or url_for("view_items"))


@app.route("/waste/<int:item_id>", methods=["POST"])
@login_required
def waste_item(item_id):
    try:
        reason = request.form.get("reason", "expired")
        try: cost = float(request.form.get("cost", 0))
        except: cost = 0
        db.mark_wasted(item_id, reason, cost, get_user_id())
        flash("Marked as wasted.", "warning")
    except: flash("Error.", "error")
    return redirect(request.referrer or url_for("view_items"))


@app.route("/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_item(item_id):
    try: db.delete_item(item_id, get_user_id()); flash("Deleted.", "info")
    except: flash("Error.", "error")
    return redirect(request.referrer or url_for("view_items"))


@app.route("/search")
@login_required
def search_items():
    user_id = get_user_id()
    try:
        query = request.args.get("q", "").strip()
        category = request.args.get("category", "")
        storage = request.args.get("storage", "")
        status = request.args.get("status", "")
        items = db.search_items(query, category, storage, status, user_id)
        today = datetime.now().date()
        for item in items:
            item["days_left"] = (datetime.strptime(item["expiry_date"], "%Y-%m-%d").date() - today).days
            exp_status, badge, _ = analyzer.get_expiry_status(item["expiry_date"])
            item["status"], item["badge"] = exp_status, badge
        return render_template("search.html", items=items, categories=db.get_categories(),
                               query=query, selected_category=category,
                               selected_storage=storage, selected_status=status)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return render_template("search.html", items=[], categories=[], query="", selected_category="", selected_storage="", selected_status="")


@app.route("/stats")
@login_required
def stats():
    user_id = get_user_id()
    try:
        days = int(request.args.get("days", 30))
        if days not in [7, 30, 90, 365]: days = 30
        return render_template("stats.html", waste_stats=db.get_waste_stats(days, user_id),
                               score=analyzer.calculate_waste_reduction_score(user_id),
                               days=days, daily_waste=db.get_daily_waste(7, user_id))
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return redirect(url_for("dashboard"))


@app.route("/recipes")
@login_required
def recipes():
    user_id = get_user_id()
    try:
        expiring = analyzer.get_priority_items(user_id)
        return render_template("recipes.html", expiring=expiring,
                               recipe=analyzer.suggest_recipe(expiring) if expiring else None,
                               categories=db.get_categories())
    except Exception as e:
        logger.error(f"Recipes error: {e}")
        return redirect(url_for("dashboard"))


@app.route("/categories")
@login_required
def categories():
    try: return render_template("categories.html", categories=db.get_categories())
    except: return redirect(url_for("dashboard"))


@app.route("/shopping-list")
@login_required
def shopping_list():
    user_id = get_user_id()
    try:
        return render_template("shopping.html", expiring=analyzer.get_priority_items(user_id),
                               shopping_items=db.get_shopping_items(user_id))
    except: return render_template("shopping.html", expiring=[], shopping_items=[])


@app.route("/shopping/add", methods=["POST"])
@login_required
def add_shopping_item():
    try:
        name = request.form.get("name", "").strip()
        if name:
            try: quantity = float(request.form.get("quantity", 1))
            except: quantity = 1
            db.add_shopping_item(name, request.form.get("category", ""), quantity,
                                 request.form.get("unit", "pcs"), get_user_id())
            flash("Added to shopping list!", "success")
        else: flash("Enter an item name.", "error")
    except: flash("Error.", "error")
    return redirect(url_for("shopping_list"))


@app.route("/shopping/purchase/<int:item_id>", methods=["POST"])
@login_required
def purchase_shopping_item(item_id):
    try: db.mark_shopping_purchased(item_id, get_user_id()); flash("Purchased!", "success")
    except: flash("Error.", "error")
    return redirect(url_for("shopping_list"))


@app.route("/shopping/delete/<int:item_id>", methods=["POST"])
@login_required
def delete_shopping_item(item_id):
    try: db.delete_shopping_item(item_id, get_user_id()); flash("Removed.", "info")
    except: flash("Error.", "error")
    return redirect(url_for("shopping_list"))


@app.route("/export")
@login_required
def export_csv():
    try:
        items = db.get_all_items(get_user_id())
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Name", "Category", "Quantity", "Unit", "Storage", "Purchase Date", "Expiry Date", "Notes"])
        for item in items:
            writer.writerow([item["id"], item["name"], item.get("category_name", ""), item["quantity"],
                           item["unit"], item["storage_location"], item["purchase_date"], item["expiry_date"], item["notes"]])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv",
                       headers={"Content-Disposition": "attachment; filename=food_inventory_export.csv"})
    except: flash("Export error.", "error"); return redirect(url_for("dashboard"))


@app.route("/api/stats")
@login_required
def api_stats():
    try: return jsonify(db.get_waste_stats(int(request.args.get("days", 30)), get_user_id()))
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/daily-waste")
@login_required
def api_daily_waste():
    try: return jsonify(db.get_daily_waste(int(request.args.get("days", 7)), get_user_id()))
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/expiring")
@login_required
def api_expiring():
    try: return jsonify(db.get_expiring_items(int(request.args.get("days", 3)), get_user_id()))
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/subscribe", methods=["POST"])
@login_required
def subscribe_notifications():
    try:
        data = request.get_json()
        if data and data.get("subscription"):
            db.save_push_subscription(data["subscription"], get_user_id())
            return jsonify({"success": True})
        return jsonify({"success": False}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/unsubscribe", methods=["POST"])
@login_required
def unsubscribe_notifications():
    try:
        data = request.get_json()
        if data and data.get("subscription"):
            db.remove_push_subscription(data["subscription"], get_user_id())
            return jsonify({"success": True})
        return jsonify({"success": False}), 400
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/check")
@login_required
def check_notifications():
    try:
        items = db.get_expiring_items(3, get_user_id())
        today = datetime.now().date()
        return jsonify([{"id": i["id"], "name": i["name"], "category": i.get("category_name", ""),
                        "expiry_date": i["expiry_date"],
                        "days_left": (datetime.strptime(i["expiry_date"], "%Y-%m-%d").date() - today).days} for i in items])
    except Exception as e: return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok"})
