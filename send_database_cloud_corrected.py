#!/usr/bin/python3
import mysql.connector
import subprocess
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
import RPi.GPIO as GPIO
import Adafruit_DHT

interval = 1 
PIR_PIN = 22
DHT_PIN = {"temperature": 26, "humidity": 26}

# Email setup
sender_email = "" #write the sender email address
sender_password = ""#write the sender password
recipients = [""] #write the receipent emmail addresses
smtp_server = "smtp.gmail.com"
smtp_port = 587

# Initialize variables for hourly checking
last_alert_time = datetime.now()

# MySQL database configuration
db_config = {
    'user': '', #write the user name of server
    'password': '', #write the password of server
    'host': '',  # Change this to 'localhost' if MySQL is on the Raspberry Pi
    'database': ''  #write the same of database
}

def create_table():
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            timestamp DATETIME,
            filesystem VARCHAR(255),
            size VARCHAR(50),
            used VARCHAR(50),
            available VARCHAR(50),
            use_percent VARCHAR(10),
            mounted_on VARCHAR(255),
            cpu_temperature FLOAT,
            cpu_usage FLOAT,
            pir_sensor VARCHAR(50),
            temperature FLOAT,
            humidity FLOAT
        )
    ''')
    connection.commit()
    cursor.close()
    connection.close()

def insert_data(data):
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor()
    for item in data:
        cursor.execute('''
            INSERT INTO sensor_data (timestamp, filesystem, size, used, available, use_percent, mounted_on, cpu_temperature, cpu_usage, pir_sensor, temperature, humidity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            item.get("Timestamp"),
            item.get("Filesystem"),
            item.get("Size"),
            item.get("Used"),
            item.get("Available"),
            item.get("Use%"),
            item.get("Mounted_On"),
            item.get("CPU_Temperature"),
            item.get("CPU_Usage"),
            item.get("PIR_Sensor"),
            item.get("Temperature"),
            item.get("Humidity")
        ))
    connection.commit()
    cursor.close()
    connection.close()

def disk_usage():
    def convert_size(size_str):
        if size_str.endswith("M"):
            size_in_mb = float(size_str[:-1])
            size_in_gb = size_in_mb / 1024
            return f"{size_in_gb:.2f}"
        elif size_str.endswith("K"):
            size_in_kb = float(size_str[:-1])
            size_in_gb = size_in_kb/(1024**2)
            return f"{size_in_gb:.2f}"
        elif size_str.endswith("G"):
            return size_str[:-1]
        elif size_str.endswith("%"):
            return size_str[:-1]
        else:
            return size_str

    command = "df -h"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)
    df_output = result.stdout
    processed_lines = []

    for line in df_output.splitlines():
        columns = line.split()
        if len(columns) >= 6:
            # Convert relevant columns
            columns[1] = convert_size(columns[1])  # Total size
            columns[2] = convert_size(columns[2])  # Used size
            columns[3] = convert_size(columns[3])  # Available size
            columns[4] = convert_size(columns[4])  # Use% (removes % sign)
        processed_lines.append(' '.join(columns))

    processed_df_output = '\n'.join(processed_lines)
    return processed_df_output


def cpu_temperature():
    command = "vcgencmd measure_temp"
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)
    cpu_temp = result.stdout.replace("temp=", "").replace("'C", "")
    return float(cpu_temp)

def cpu_usage():
    command = 'top -bn1 | grep "Cpu(s)"'
    result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, text=True)
    output = result.stdout.strip()
    cpu_usage_parts = output.split(",")
    idle_cpu = float(cpu_usage_parts[3].split()[0].replace("%", "").strip())
    user_cpu = 100 - idle_cpu
    return user_cpu

def pir_sensor(pin):
    try:
        if GPIO.input(pin):
            return "Motion Detected"
        else:
            return "No Motion Detected"
    except Exception as e:
        return f"Sensor Error: {e}"

def read_dht11(pin, data_type):
    sensor = Adafruit_DHT.DHT11
    humidity, temperature = Adafruit_DHT.read(sensor, pin)
    if humidity is not None and temperature is not None:
        if data_type == "temperature":
            return temperature
        elif data_type == "humidity":
            return humidity
    return None

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = ", ".join(recipients)
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipients, msg.as_string())
        server.close()
        print("Email sent successfully!")
    except Exception as e:
        print(f"Failed to send email: {e}")

def parse_disk_usage(output):
    lines = output.splitlines()[1:]  # Skip the header
    parsed_data = []
    for line in lines:
        parts = line.split()
        if len(parts) > 5:
            filesystem, size, used, available, use_percent, mounted_on = parts[:6]
            parsed_data.append({
                "Filesystem": filesystem,
                "Size": size,
                "Used": used,
                "Available": available,
                "Use%": use_percent,
                "Mounted_On": mounted_on
            })
    return parsed_data

def check_conditions(parsed_data):
    alerts = []

    # Check disk usage
    for entry in parsed_data:
        use_percent = int(entry["Use%"].replace('%', ''))
        if use_percent > 80:
            alerts.append(f"Disk Usage Alert: {entry['Filesystem']} is at {entry['Use%']} usage.")

    # Check CPU temperature
    cpu_temp = cpu_temperature()
    if cpu_temp > 80:
        alerts.append(f"CPU Temperature Alert: CPU temperature is {cpu_temp}°C.")

    # Check CPU usage
    cpu_use = cpu_usage()
    if cpu_use > 80:
        alerts.append(f"CPU Usage Alert: CPU usage is {cpu_use}%.")

    # Check PIR sensor
    pir_status = pir_sensor(PIR_PIN)
    if "Sensor Error" in pir_status:
        alerts.append(f"PIR Sensor Alert: {pir_status}.")

    return alerts

def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(PIR_PIN, GPIO.IN)
    create_table()
    global last_alert_time

    while True:
        output = disk_usage()
        parsed_data = parse_disk_usage(output)
        for entry in parsed_data:
            entry["Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry["CPU_Temperature"] = cpu_temperature()
            entry["CPU_Usage"] = cpu_usage()
            entry["PIR_Sensor"] = pir_sensor(PIR_PIN)
            entry["Temperature"] = read_dht11(DHT_PIN["temperature"], "temperature")
            entry["Humidity"] = read_dht11(DHT_PIN["humidity"], "humidity")
        insert_data(parsed_data)

        alerts = check_conditions(parsed_data)

        # Check if an hour has passed since the last alert
        if datetime.now() >= last_alert_time + timedelta(minutes=1):
            if alerts:
                subject = "Hourly Sensor and System Alerts"
                body = "\n\n".join(alerts)
                send_email(subject, body)
            last_alert_time = datetime.now()

        time.sleep(interval)

if __name__ == "__main__":
    main()
