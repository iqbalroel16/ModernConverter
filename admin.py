from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

USAGE_LOG = 'usage.log'

# Decorator for admin login required
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    usage_count = 0
    if os.path.exists(USAGE_LOG):
        with open(USAGE_LOG, 'r') as f:
            usage_count = len(f.readlines())
    return render_template('admin_dashboard.html', usage_count=usage_count)

# ...existing code...
