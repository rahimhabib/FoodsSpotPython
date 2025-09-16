from flask import Flask, request, jsonify
from geopy.distance import geodesic
import requests
import json
import logging
import math
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# Configure logging for the application
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# ---
# Environment Variable Configuration
# It's a security best practice to load sensitive information from environment variables
# to avoid hardcoding credentials in your source code.
# ---

# Load sensitive variables from the environment
WHATSAPP_BUSINESS_ID = os.getenv('WHATSAPP_BUSINESS_ID')
ACCESS_TOKEN = os.getenv('WHATSAPP_ACCESS_TOKEN')
PHONE_NUMBER_ID = os.getenv('WHATSAPP_PHONE_NUMBER_ID')

EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
# To handle multiple emails from a single environment variable, we split the string by commas
EMAIL_RECEIVER_STR = os.getenv('EMAIL_RECEIVER')
EMAIL_CC_STR = os.getenv('EMAIL_CC')
EMAIL_RECEIVER = EMAIL_RECEIVER_STR.split(',') if EMAIL_RECEIVER_STR else []
EMAIL_CC = EMAIL_CC_STR.split(',') if EMAIL_CC_STR else []

SMTP_SERVER = 'smtp.hostinger.com'
SMTP_PORT = 587

# Hardcoded branch locations with names and coordinates
BRANCH_LOCATIONS = {
    "Foods Spot FB Area": (24.9268539, 67.0726341),
    "Foods Spot New Karachi Branch": (24.9668316, 67.0682923)
}

# Assumed costs and speeds
COST_PER_KM = 50.0  # PKR per kilometer
AVERAGE_SPEED_KMPH = 25.0 # Average speed in km/h
MIN_COOKING_TIME_MINS = 30.0 # Minimum cooking time
MIN_DELIVERY_CHARGE_PKR = 100.0 # Minimum delivery charge

def round_up_to_nearest_five(x):
    """Rounds a number up to the nearest 5."""
    return math.ceil(x / 5) * 5

def round_up_to_nearest_ten(x):
    """Rounds a number up to the nearest 10."""
    return math.ceil(x / 10) * 10

@app.route('/')
def home():
    return "The API is running!"

@app.route('/calculate-delivery', methods=['POST'])
def calculate_delivery():
    """
    Calculates delivery details for a customer's location.
    The customer's location is expected in the request body as JSON.
    Example JSON payload:
    {
        "customer_latitude": 24.93,
        "customer_longitude": 67.08
    }
    """
    try:
        # Get the request body from ManyChat
        data = request.get_json()
        app.logger.info(f"Received data from ManyChat: {json.dumps(data)}")

        # Check if the required fields are in the payload
        if not data or 'customer_latitude' not in data or 'customer_longitude' not in data:
            app.logger.error("Invalid input: Missing customer_latitude or customer_longitude.")
            return jsonify({"error": "Invalid input. Please provide customer_latitude and customer_longitude."}), 400

        customer_coords = (float(data['customer_latitude']), float(data['customer_longitude']))
        
        results = []
        nearest_branch_info = None
        min_distance = float('inf')

        # Calculate distance, time, and cost for each branch
        for branch_name, branch_coords in BRANCH_LOCATIONS.items():
            distance_km = geodesic(customer_coords, branch_coords).km
            
            # Calculate estimated time and apply new rules
            estimated_time_travel = (distance_km / AVERAGE_SPEED_KMPH) * 60
            estimated_time_total = estimated_time_travel + MIN_COOKING_TIME_MINs
            estimated_time_rounded = round_up_to_nearest_five(estimated_time_total)
            
            # Calculate total amount and apply new rules
            total_amount_raw = distance_km * COST_PER_KM
            total_amount_with_min = max(total_amount_raw, MIN_DELIVERY_CHARGE_PKR)
            total_amount_rounded = round_up_to_nearest_ten(total_amount_with_min)

            branch_info = {
                "branch_name": branch_name,
                "total_kilometers": round(distance_km, 2),
                "estimated_timing_minutes": estimated_time_rounded,
                "total_amount_pkr": total_amount_rounded
            }
            results.append(branch_info)

            # Find the nearest branch
            if distance_km < min_distance:
                min_distance = distance_km
                nearest_branch_info = branch_info

        # Prepare the final response for ManyChat in a simple key-value format
        response_content = {
            "nearest_branch_name": nearest_branch_info["branch_name"],
            "nearest_branch_total_kilometers": str(nearest_branch_info["total_kilometers"]),
            "nearest_branch_estimated_timing_minutes": str(nearest_branch_info["estimated_timing_minutes"]),
            "nearest_branch_total_amount_pkr": str(nearest_branch_info["total_amount_pkr"])
        }
        
        app.logger.info(f"Sending response: {json.dumps(response_content)}")
        return jsonify(response_content)

    except Exception as e:
        app.logger.error(f"An error occurred: {e}", exc_info=True)
        return jsonify({
            "version": "v2",
            "content": {
                "messages": [
                    {
                        "type": "text",
                        "text": "Sorry, an error occurred while calculating the delivery details. Please try again."
                    }
                ]
            }
        }), 500

def send_email_notification(subject, body):
    """Sends an email notification."""
    try:
        # --- DEBUGGING: Log the values being used ---
        app.logger.info(f"Attempting to send email.")
        app.logger.info(f"SENDER: {EMAIL_SENDER}")
        app.logger.info(f"RECEIVERS: {EMAIL_RECEIVER}")
        app.logger.info(f"CC: {EMAIL_CC}")
        # --- END DEBUGGING ---

        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        # Join the list of recipients into a comma-separated string for the 'To' header
        msg['To'] = ", ".join(EMAIL_RECEIVER)
        if EMAIL_CC:
            msg['Cc'] = ", ".join(EMAIL_CC)
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        # Pass the list of recipients directly to the sendmail function
        all_recipients = EMAIL_RECEIVER + EMAIL_CC
        server.sendmail(EMAIL_SENDER, all_recipients, msg.as_string())
        server.quit()
        app.logger.info("Email notification sent successfully.")
    except Exception as e:
        app.logger.error(f"Failed to send email: {e}", exc_info=True)
        return False
    return True

def send_whatsapp_message(customer_name, order_details, total_amount, delivery_address, recipient_phone_number):
    """Sends a WhatsApp message using a pre-approved template."""
    url = f'https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages'
    headers = {
        'Authorization': f'Bearer {ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # NOTE: The recipient phone number is hardcoded for testing.
    # In a real scenario, you would use recipient_phone_number from the ManyChat payload.
    recipient_phone_number = '923332252591'

    # Updated payload to use a template message
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_phone_number,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {
                "code": "en_US"
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        app.logger.info(f"WhatsApp API response: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error sending WhatsApp message: {e}", exc_info=True)
        return False

@app.route('/send-whatsapp', methods=['POST'])
def handle_whatsapp_request():
    data = request.json
    success = send_whatsapp_message(
        customer_name=data.get('customer_name'),
        order_details=data.get('order_details'),
        total_amount=data.get('total_amount'),
        delivery_address=data.get('delivery_address'),
        recipient_phone_number=data.get('recipient_phone')
    )
    if success:
        return jsonify({'status': 'success', 'message': 'WhatsApp message sent.'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Failed to send WhatsApp message.'}), 500

@app.route('/send-order-confirmation', methods=['POST'])
def handle_order_confirmation_request():
    data = request.json
    
    email_subject = "Your Foods Spot Order Confirmation"
    email_body = f"""
    Hello {data.get('customer_name')},

    Thank you for your order! Your order has been placed and will be delivered shortly.

    ---
    Order Details:
    ---
    
    Order: {data.get('order_details')}
    Total Amount: {data.get('total_amount')} PKR
    
    ---
    Delivery Information:
    ---
    
    Name: {data.get('customer_name')}
    Phone Number: {data.get('customer_phone')}
    Delivery Address: {data.get('delivery_address')}
    
    Special Instructions:
    {data.get('special_instructions')}
    
    ---
    
    Thank you for choosing Foods Spot!
    
    Sincerely,
    The Foods Spot Team
    """
    
    success = send_email_notification(email_subject, email_body)
    if success:
        return jsonify({'status': 'success', 'message': 'Email notification sent.'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Failed to send email notification.'}), 500

if __name__ == '__main__':
    # Verify that all required environment variables are set
    required_vars = [
        'WHATSAPP_BUSINESS_ID', 'WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_PHONE_NUMBER_ID',
        'EMAIL_SENDER', 'EMAIL_PASSWORD', 'EMAIL_RECEIVER'
    ]
    for var in required_vars:
        if not os.getenv(var):
            raise RuntimeError(f"Environment variable '{var}' is not set. Please set it before running the application.")

    # In production, you would use a WSGI server like Gunicorn
    app.run(host='0.0.0.0', port=5000)
