"""User-facing catalogue of business reports."""
from flask import Blueprint, render_template

reports = Blueprint('reports', __name__)


@reports.get('/reports')
def index():
    return render_template('reports.html')
