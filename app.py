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

# Replace with your WhatsApp Business Account ID, Access Token, and Phone Number ID
# NOTE: This information is sensitive. It's best practice to use environment variables in a production environment.
# You MUST replace these placeholders with your actual values.
WHATSAPP_BUSINESS_ID = '515158285015725'
ACCESS_TOKEN = 'EAARi2FEsmAcBPdMggK6qZBridtYb2r0y19xpEg7w1JTdYwUVOImLIgz9S18SahKLEidyH4r6018vtgUB5Sw6UARrQ2qtyTZC7MahtU2HW47tjBBuDMGhZBZCgWyR0ukSxkcolclIDLh6oZCYk5g8Tf6Mo9OOYR8yBv9bKbpBj89ogNyxUIkksp0r1zA8iyt52pOnQ6ROpCDv1VFQxkteEN7w3XaJP3LRDrERLpSOjZAgUZD'
PHONE_NUMBER_ID = '559620697225153'

# Email configuration
# NOTE: This information is sensitive. Use environment variables in a production environment.
EMAIL_SENDER = 'fsaiagent@foodsspot.com'
EMAIL_PASSWORD = 'L@khani#123' # Use an app-specific password if using Gmail
EMAIL_RECEIVER = 'lakhanino1@gmail.com' # The email address to receive order notifications
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
            estimated_time_total = estimated_time_travel + MIN_COOKING_TIME_MINS
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
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
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

@app.route('/send-email', methods=['POST'])
def handle_email_request():
    data = request.json
    
    email_subject = "New Order Received from Mobile AI Agent"
    email_body = f"""
    A new order has been received via your mobile AI agent.

    Customer Details:
    Name: {data.get('customer_name')}
    Contact #: {data.get('customer_phone')}
    Address: {data.get('delivery_address')}

    Order Details:
    {data.get('order_details')}

    Amount: {data.get('total_amount')} PKR

    Special Instructions:
    {data.get('special_instructions')}
    
    Thank you!
    """
    
    success = send_email_notification(email_subject, email_body)
    if success:
        return jsonify({'status': 'success', 'message': 'Email notification sent.'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Failed to send email notification.'}), 500

if __name__ == '__main__':
    # In production, you would use a WSGI server like Gunicorn
    app.run(host='0.0.0.0', port=5000)
