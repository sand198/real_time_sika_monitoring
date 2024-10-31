#!/usr/bin/python3
import time
from datetime import datetime, timedelta
import RPi.GPIO as GPIO
import os
import cv2
import threading
from ultralytics import YOLO
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import gps
import requests
from PIL import Image
from pydub import AudioSegment
from pydub.playback import play
from ftplib import FTP
import csv
import numpy as np

#GPIO setup
PIR_PIN = 22
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

#Camera setup
camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)

#set the model
model = YOLO("/home/pi/Desktop/sika_detection/best.pt")

#Email setup
sender_email = ""   #put the sender email address
sender_password = ""  #put the sender password through 2-step verification
recipients = [""]  #email u want to notify
smtp_server = "smtp.gmail.com"
smtp_port = 587

# infeomation connettion FTP
ftp_server = ''  #server name
ftp_username = ''  #server username
ftp_password = '' #server password
ftp_directory = ''  # Path change to server ftp
ftp_csv = ''

university_logo_path = "" #file path for the logo
audio_file_path = "" #file path for the audio
local_csv_path = "" #3local directory file path to save the csv file

#def get_coordinates():
#    session = gps.gps()
#    session.stream(gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
#    try:
#        report = session.next()
#        if report["class"] == "TPV":
#            return report.lat, report.lon
#    except Exception as e:
#        print(f"GPS Error: {e}")
#        return None, None
#latitude, longitude = get_coordinates()
latitude = "42.382238"
longitude = "141.030967"
google_maps_url = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}"
# Track last email sent time
last_email_time = datetime.now() - timedelta(minutes=30)
last_message_time = datetime.now() - timedelta(minutes=30)


def generate_ultrasonic_sound(frequency=16000, duration=5000):
    # Generate a 22 kHz sound wave
    sample_rate = 44100  # Sample rate in Hz
    samples = np.array(
        [np.sin(2 * np.pi * frequency * t / sample_rate) for t in range(int(sample_rate * duration / 1000))]
    ).astype(np.float32)

    # Normalize to 0.5 for pydub
    samples *= 0.5

    # Create an AudioSegment
    sound = AudioSegment(
        samples.tobytes(),
        frame_rate=sample_rate,
        sample_width=4,  # 32-bit samples
        channels=1  # Mono
    )

    # Export as a WAV file
    sound.export(audio_file_path, format="wav")
    print(f"Ultrasonic sound generated and saved as {audio_file_path}.")

def play_audio():
    generate_ultrasonic_sound()  # Generate the ultrasonic sound
    sound = AudioSegment.from_wav(audio_file_path)
    play(sound)

def send_line_message(message_body):
    global last_message_time
    current_time = datetime.now()

    # Check if the last message was sent less than an hour ago
    if current_time - last_message_time < timedelta(minutes=30):
        return

    # Format the timestamp
    formatted_timestamp = current_time.strftime("%Y/%m/%d - %H:%M:%S")

    # Construct the message
    message = f"""
    {message_body}
    \nSent at: {formatted_timestamp}
    \nSika Deer: Importance and Impact:
    Sika Deer are vital to ecosystems, promoting biodiversity and forest regeneration. However, they can damage crops in agricultural areas, causing economic losses and conflicts with farming. Managing their populations is esssential to balance conservation and agriculture.
    """

#    # Define the headers and payload for the LINE Notify API
    headers = {
        'Authorization': 'Bearer UAIoNZJg9IgDOzmGgF56xJsjIuo8taLs70sQlaYi4I9'
    }
    payload = {'message': message}
    files = {'imageFile': open('logo.jpg', 'rb')}

    try:
#        # Send the message to LINE Notify API
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, data=payload, files = files)
        response.raise_for_status()  # Raise an error if the request failed
        last_message_time = current_time
        print("Message sent successfully")
    except requests.RequestException as e:
        print(f"Failed to send message: {e}")

def draw_bounding_boxes(img, boxes):
    bounding_boxes_drawn = False
    for box in boxes:
        x_min, y_min, x_max, y_max, conf, _ = box
        if conf > 0.7:
            cv2.rectangle(img, (int(x_min), int(y_min)), (int(x_max), int(y_max)), (0, 0, 255), 10)
            text = f"Conf: {conf:.2f}"
            (w, h), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 2, 5)
            cv2.rectangle(img, (int(x_min), int(y_min) - h - _), (int(x_min) + w, int(y_min) + _), (255, 255, 255), thickness = cv2.FILLED)
            cv2.rectangle(img, (int(x_min), int(y_min) - h - _), (int(x_min) + w, int(y_min) + _), (255, 0, 0), 5)
            cv2.putText(img, text, (int(x_min), int(y_min) - 10), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 0), 5)
            bouning_boxes_drawn = True
    return img, bounding_boxes_drawn

def send_ftp_file(server, username, password, local_file_path, remote_directory):
    try:
        # Connect to the FTP server
        ftp = FTP(server)
        ftp.login(user=username, passwd=password)

        # Navigate to the specified directory on the server
        if remote_directory:
            try:
                ftp.cwd(remote_directory)
            except Exception as e:
                print(f"Failed to change directory to {remote_directory}. Error: {str(e)}")
                ftp.quit()
                return

        # Extract the file name from the local file path
        file_name = os.path.basename(local_file_path)

        # Open the file and send it to the server via FTP
        with open(local_file_path, 'rb') as file:
            ftp.storbinary(f'STOR {file_name}', file)

        # Disconnect from the server
        ftp.quit()

        print(f'File {local_file_path} uploaded successfully to {remote_directory}.')

    except Exception as e:
        print(f'Failed to upload file. Error: {str(e)}')

def capture_image():
    global last_email_time, last_message_time
    while True:
        if GPIO.input(PIR_PIN):
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            folder_name = "Image"
            save_path = os.path.join(folder_name)

            os.makedirs(save_path, exist_ok=True)

            original_image_path = os.path.join(save_path, f"Original_Image_{timestamp}.jpg")
            bbox_image_path = os.path.join(save_path, f"BBox_Image_{timestamp}.jpg")

            ret, frame = camera.read()
            if ret:
                start_time = time.time()
                cv2.imwrite(original_image_path, frame)

                results = model(frame)
                boxes = results[0].boxes.data.tolist()

                frame_with_boxes, boxes_detected = draw_bounding_boxes(frame.copy(), boxes)
                cv2.imwrite(bbox_image_path, frame_with_boxes)
                print(f"Images Captured: {original_image_path}, {bbox_image_path}")

                num_boxes = len(boxes)
                latency = time.time() - start_time
                email_sent_time = datetime.now()
                line_message_time = datetime.now()
                buzzer_time = datetime.now()

                if boxes:
                    subject = "Alert: Sika Deer Detected"
                    send_email(subject, timestamp, bbox_image_path)
                    send_line_message("Alert: Sika deer detected!")
                    play_audio()

                log_data = {
                    'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Image': os.path.basename(bbox_image_path),
                    'No of Bounding Boxes': num_boxes,
                    'Latency of Creating Bounding Boxes': f"{latency:.2f} seconds",
                    'Email Sent Time': email_sent_time.strftime("%Y-%m-%d %H:%M:%S"),
                    'Time for Sending Line': line_message_time.strftime("%Y-%m-%d %H:%M:%S"),
                    'Buzzer Sound Time': buzzer_time.strftime("%Y-%m-%d %H:%M:%S")
                }

                # Append to local CSV file
                append_to_csv(log_data, local_csv_path)

                # Upload the updated CSV file to FTP server
                send_ftp_file(ftp_server, ftp_username, ftp_password, local_csv_path, ftp_csv)

                # Upload images to FTP server
                upload_file_to_ftp(ftp_server, ftp_username, ftp_password, original_image_path, ftp_directory)
                upload_file_to_ftp(ftp_server, ftp_username, ftp_password, bbox_image_path, ftp_directory)

                try:
                    os.remove(original_image_path)
                    os.remove(bbox_image_path)
                    print(f"Deleted images: {original_image_path}, {bbox_image_path}")
                except Exception as e:
                    print(f"Failed to delete images. Error: {str(e)}")

def append_to_csv(log_data, local_csv_path):
    file_exists = os.path.isfile(local_csv_path)

    with open(local_csv_path, 'a', newline='') as csvfile:
        fieldnames = ['Timestamp', 'Image', 'No of Bounding Boxes', 'Latency of Creating Bounding Boxes', 'Email Sent Time', 'Time for Sending Line', 'Buzzer Sound Time']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()  # write header only if file does not exist
        writer.writerow(log_data)

def upload_file_to_ftp(server, username, password, file_path, ftp_directory):
    try:
        # Connect to the FTP server
        ftp = FTP(server)
        ftp.login(user=username, passwd=password)

        # Navigate to the specified directory on the server
        if ftp_directory:
            ftp.cwd(ftp_directory)

        # Open the file and send it to the server via FTP
        with open(file_path, 'rb') as file:
            ftp.storbinary(f'STOR {file_path.split("/")[-1]}', file)

        # Disconnect from the server
        ftp.quit()

        print(f'File {file_path} uploaded successfully to {ftp_directory}.')

    except Exception as e:
        print(f'Failed to upload file. Error: {str(e)}')

def send_email(subject, body, save_path):
    global last_email_time
    current_time = datetime.now()
    if current_time - last_email_time < timedelta(minutes=30):
        return
    formatted_timestamp = current_time.strftime("%Y/%m/%d - %H:%M:%S")
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"{subject.upper()} - {formatted_timestamp}"

    # Add text body
    html_body = f"""
    <html>
    <body>
        <h1>{subject.upper()}</h1>
        <p>{body}</p>
        <p>Image path: {save_path}</p>
        <h2>Importance of Sika Deer</h2>
        <p>Sika Deer plays an important role in their ecosystem. As a keystone species, they help to maintain plant community structure and promote biodiversity. Their grazing habits contribute to the health of forest ecosystem by controlling undergrowth and facilitating the regeneration of various plant species. Additionally, Sika deer are a significant part of the food web, serving as a prey of predators and contributing to the balance of their natural habitat.</p>
        <h2>Impact on Agricultural Production</h2>
        <p>In agricultural areas, Sika deer can have a substantial negative impacts. Their feeding habits often lead to significant damage to crops, including the destruction of young plants and reduction in yield. This can result in economic losses for farmers and create conflict between wildlife conservation efforts and agricultural practices. Managing Sika deer populations and implementing effective deterrents is essential to mitigate their impact and protect agricultural productivity.</p>
        <p>Email Sent at: {formatted_timestamp}</p>
        <img src="cid:university_logo" alt="University Logo" width = "200" height "200"><br>
        <a href="{google_maps_url}">Current Location on Google Maps</a>/
    </body>
    </html>
    """
    msg.attach(MIMEText(html_body, "html"))

    # Attach image
    with open(university_logo_path, "rb") as img:
        logo = MIMEImage(img.read())
        logo.add_header("Content-ID", "<university_logo>")
        msg.attach(logo)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipients, msg.as_string())
            last_email_time = current_time
            print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

def setup_pir_sensor():
    try:
        time.sleep(2)
        print("Ready")
        # Start the image capture thread
        image_thread = threading.Thread(target=capture_image)
        image_thread.daemon = True
        image_thread.start()

        # Main loop for PIR sensor
        while True:
            if GPIO.input(PIR_PIN):
                # Ensure capture_image is only called once per trigger
                if not image_thread.is_alive():
                    image_thread = threading.Thread(target=capture_image)
                    image_thread.daemon = True
                    image_thread.start()
            time.sleep(2)  # Adjust as needed
    except KeyboardInterrupt:
        print("Quit")
        GPIO.cleanup()
        camera.release()

if __name__ == "__main__":
    setup_pir_sensor()

