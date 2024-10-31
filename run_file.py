#!/usr/bin/python3
import RPi.GPIO as GPIO  
import subprocess
import time

BUTTON_PIN = 13

def button_callback(channel):
    print(f"Button on pin {channel} was pushed")
    # Run both Python scripts in parallel
    subprocess.Popen(['/usr/bin/python3', '/home/pi/Desktop/sika_detection/send_alert_messages.py'])
    subprocess.Popen(['/usr/bin/python3', '/home/pi/Desktop/sika_detection/send_database_cloud_corrected.py'])

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
GPIO.setup(BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

GPIO.add_event_detect(BUTTON_PIN, GPIO.RISING, callback=button_callback, bouncetime=300)

# Keep the script running
try:
    while True:
        time.sleep(0.5)  # Prevent the script from exiting
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()  # Clean up GPIO on exit
