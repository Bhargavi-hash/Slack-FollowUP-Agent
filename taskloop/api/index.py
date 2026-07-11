from flask import Flask

app = Flask(__name__)

@app.route("/")
def health_check():
    return "TaskLoop is alive"

@app.route("/slack/commands", methods=["POST"])
def slack_commands():
    return "", 200  # placeholder for now