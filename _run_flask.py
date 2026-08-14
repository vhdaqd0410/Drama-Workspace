import sys, os
sys.path.insert(0, 'backend')
os.environ["DRAMA_DESKTOP"] = "1"
from app import create_app
app = create_app()
print("Flask OK, routes:", len(list(app.url_map.iter_rules())))
app.run(host="127.0.0.1", port=5100, debug=False)
