from flask import Flask, render_template, url_for, request, session, redirect
from pymongo import MongoClient
import bcrypt
from datetime import datetime, timedelta
from random import choice
import json
import requests

app = Flask(__name__)
with open("config.json") as config_file:
    config = json.load(config_file)

abstractapi_key = config.get("abapi_key")

if abstractapi_key:
    response = requests.get(f"https://ipgeolocation.abstractapi.com/v1/?api_key={abstractapi_key}")
    print(response.status_code)
    # print(response.content)

    if response.status_code == 200:
        with open("log.txt", "a", encoding="utf-8") as log_file:
            log_file.write(response.content.decode("utf-8"))
            log_file.write("\nNext\n\n\n")
    else:
        print("Error fetching data from the API.")
else:
    print("AbstractAPI key not found in the configuration file.")
    
mongo_connection_string = config.get("mongo_connection_string")

if mongo_connection_string:
    client = MongoClient(mongo_connection_string)
else:
    print("Error: MongoDB connection string not found in the config file.")
db = client["LSM"]
user_collection = db["users"]
cleaning_collection = db["cleaning_options"]
feedback = db["feedback_entries"]
lost = db["lost_entries"]

app.secret_key = "mysecret"
app.config["UPLOAD_FOLDER"] = "static/images"


@app.route("/image/<filename>")
def get_image(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


def get_remaining_cleanings(username):
    user = user_collection.find_one({"name": username})
    if user:
        remaining_cleanings = user.get("remaining_cleanings", 70)
        return remaining_cleanings
    else:
        return 0


def is_time_within_range(existing_time, new_time, minutes_range):
    if existing_time is not None and new_time is not None:
        existing_time = datetime.strptime(existing_time, "%I:%M %p")
        new_time = datetime.strptime(new_time, "%I:%M %p")
        time_difference = (new_time - existing_time).total_seconds()
        return abs(time_difference) <= minutes_range * 60
    else:
        return False


@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("clean"))
    return render_template("index.html")


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        entered_username = request.form["username"]
        entered_password = request.form["pass"]
        user = user_collection.find_one({"name": entered_username})

        if user and bcrypt.checkpw(entered_password.encode("utf-8"), user["password"]):
            session["username"] = entered_username
            return redirect(url_for("clean"))
        return """
    <script>
        alert("Invalid username/password combination!");
        window.location.href = "/..";
    </script>
    """
    return render_template("login.html")


@app.route("/register", methods=["POST", "GET"])
def register():
    room_number = "0"
    remaining_cleanings = 70
    if request.method == "POST":
        existing_user = user_collection.find_one({"name": request.form["username"]})
        if existing_user is None:
            hashpass = bcrypt.hashpw(
                request.form["password"].encode("utf-8"), bcrypt.gensalt()
            )
            user_collection.insert_one(
                {
                    "name": request.form["username"],
                    "password": hashpass,
                    "room_number": request.form["room_number"],
                    "phone_number": request.form["phone_number"],
                    "remaining_cleanings": int(
                        request.form.get("remaining_cleanings", 70)
                    ),
                }
            )
            session["username"] = request.form["username"]
            return redirect(url_for("index"))
        return """
    <script>
        alert("That username already exists!");
        window.location.href = "/register";
    </script>
    """
    return render_template(
        "register.html",
        room_number=room_number,
        remaining_cleanings=remaining_cleanings,
    )


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return redirect(url_for("index"))

from flask import redirect, url_for

@app.route("/clean", methods=["GET", "POST"])
def clean():
    room_number = None
    cleaning_option = request.form.get("cleaning_option")
    selected_time = request.form.get("time_for_cleaning")

    if "username" in session:
        user = user_collection.find_one({"name": session["username"]})
        if user:
            room_number = user.get("room_number", "0")
    else:
        return redirect(url_for("index"))

    assigned_captain_message = ""

    if request.method == "POST":
        existing_cleanings = cleaning_collection.find(
            {"room_number": room_number, "time_for_cleaning": {"$exists": True}}
        )
        captain_assigned = False

        for existing_cleaning in existing_cleanings:
            if is_time_within_range(
                existing_cleaning["time_for_cleaning"], selected_time, 1440
            ):
                assigned_captain = existing_cleaning.get("assigned_captain")
                assigned_captain_phone = existing_cleaning.get("captain_phone")
                cleaning_option = existing_cleaning.get("cleaning_option")
                scheduled_time = existing_cleaning["time_for_cleaning"]
                next_available_time = datetime.strptime(
                    scheduled_time, "%I:%M %p"
                ) + timedelta(hours=24)
                next_available_time_str = next_available_time.strftime("%I:%M %p")

                assigned_captain_message = f"You cannot schedule another cleaning within the next 24 hours of the existing cleaning request. Captain {assigned_captain} has already been appointed to clean your room {room_number} with {cleaning_option} at {scheduled_time} today."

                captain_assigned = True

        if captain_assigned:
            return f'<script>alert("{assigned_captain_message}"); window.location.href = "/clean";</script>'

        captains = {
            "Gopinath": "+1234567890",
            "Ajith": "9876543210",
            "Vijay": "9783748372",
            "Leo Das": "9655116789",
            "Parthiban": "69870567893",
            "Nihal Thomas": "7897656790",
            "Abdul Mohammad": "9678465792",
            "Ragavendra": "9537283692",
        }

        assigned_captain = choice(list(captains.keys()))
        assigned_captain_phone = captains[assigned_captain]

        if cleaning_option == "broom":
            cleaning_option = "Broom"
        elif cleaning_option == "mop":
            cleaning_option = "Mop"
        elif cleaning_option == "both":
            cleaning_option = "Both Broom and Mop"
        else:
            cleaning_option = "Unknown"

        cleaning_data = {
            "room_number": room_number,
            "cleaning_option": cleaning_option,
            "time_for_cleaning": selected_time,
            "assigned_captain": assigned_captain,
            "captain_phone": assigned_captain_phone,
        }

        assigned_captain_message = f"Captain {assigned_captain} has been assigned to clean your room {room_number} at {selected_time} using {cleaning_option}. Contact details {assigned_captain_phone}"
        cleaning_collection.insert_one(cleaning_data)
        remaining_cleanings = get_remaining_cleanings(session["username"])

        return f'<script>alert("{assigned_captain_message}"); window.location.href = "/";</script>'

    remaining_cleanings = get_remaining_cleanings(session["username"])
    return render_template(
        "temp.html",
        assigned_captain_message=assigned_captain_message,
        room_number=room_number,
        remaining_cleanings=remaining_cleanings,
    )


@app.route("/events")
def events():
    return render_template("events.html")


@app.route("/emergency")
def emergency():
    return render_template("s1.html")


@app.route("/wifi")
def wifi():
    return render_template("s2.html")


@app.route("/index_copy")
def index_copy():
    return render_template("index_copy.html")


@app.route("/feedback_form")
def feedback_form():
    return render_template("feedback_form.html")


@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    feedback_data = {
        "name": request.form["name"],
        "email": request.form["email"],
        "feedback": request.form["complaint"],
    }
    feedback.insert_one(feedback_data)
    return redirect(url_for("thank_you_feedback"))


@app.route("/thank_you_feedback")
def thank_you_feedback():
    return """
    <script>
        alert("Thank you for your feedback! Due action will be taken regarding this!");
        window.location.href = "/";
    </script>
    """


@app.route("/found")
def found():
    return render_template("found.html")


@app.route("/submit_item", methods=["POST"])
def submit_item():
    item_data = {
        "name": request.form["name"],
        "description": request.form["description"],
        "location": request.form["location"],
    }
    lost.insert_one(item_data)
    return redirect(url_for("thank_you_item"))


@app.route("/thank_you_item")
def thank_you_item():
    return """
    <script>
        alert("Thank you for submitting the item!");
        window.location.href = "/";
    </script>
    """


@app.route("/<path:undefined_route>")
def catch_all(undefined_route):
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
