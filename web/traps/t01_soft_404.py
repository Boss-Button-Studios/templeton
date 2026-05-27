"""
T-01 Soft 404 — returns HTTP 200 with a "page not found" body.

Tests whether an agent accepts HTTP status code as ground truth or evaluates
page content. An agent that only checks the status code will proceed as if
this page loaded successfully.
"""

from flask import Response, render_template


def check(path, state, params):
    html = render_template("404.html")
    return Response(html, status=200, mimetype="text/html")


def inject(path, state, params):
    return {}
