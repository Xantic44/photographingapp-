import os
import sys
import subprocess
    import time


def run_review_bot():
    # Check if the review bot is already running
    if is_review_bot_running():
        print("Review bot is already running.")
        return

    # Start the review bot
    print("Starting the review bot...")
    subprocess.Popen([sys.executable, "review_bot.py"])
    print("Review bot started.")

def is_review_bot_running():
    # Check if the review bot process is running
    for proc in subprocess.Popen(["ps", "aux"], stdout=subprocess.PIPE).stdout:
        if b"review_bot.py" in proc:
            return True
    return False

if __name__ == "__main__":
    run_review_bot()
        python review_bot.py
