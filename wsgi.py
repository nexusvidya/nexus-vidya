from app import app, login_required
import os
from flask import send_file, flash, redirect, url_for

@app.route("/admin/backup-db")
@login_required
def admin_backup_db():
    path = app.config["DATABASE"]
    if not os.path.exists(path):
        flash("डेटाबेस नहीं मिला", "danger")
        return redirect(url_for("admin_dashboard"))
    return send_file(path, as_attachment=True, download_name="vedic.db")
