from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "WORKING 100% ✅"

if __name__ == "__main__":
    app.run(port=8000, debug=False)