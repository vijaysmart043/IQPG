from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def overview():
    return render_template("overview.html")

@app.route("/health")
def health():
    return "IQPG backend running successfully"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
