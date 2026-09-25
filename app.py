#!/usr/bin/env python3
"""
Nexus Vidya CMS - Knowledge platform for Astrology, Vastu, Vedic Neurology,
Name Numerology, Current Affairs and any subject you study
"""

import os
import re
import html as html_module
import sqlite3
import uuid
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from markupsafe import Markup, escape
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, abort, jsonify
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nexus-vidya-secret-key-2026")
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "instance", "vedic.db")

ALLOWED_IMAGE = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
ALLOWED_VIDEO = {"mp4", "webm", "mov", "avi", "mkv"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
