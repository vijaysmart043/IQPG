from flask import Flask

app = Flask(__name__)

@app.route("/")
def health():
    return "IQPG Backend is running successfully"

# Import your existing logic here if needed
# Example:
# from routes.exam import exam_bp
# app.register_blueprint(exam_bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
